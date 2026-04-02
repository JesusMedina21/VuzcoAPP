from django.contrib import admin
from django.contrib.auth.models import Group
from .models import *
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from django.utils.safestring import mark_safe
from django.forms.widgets import Input
from social_django.models import UserSocialAuth
from django import forms
import cloudinary.uploader

from django import forms
import re

def _extract_public_id(file_name_or_url):
    """
    Extrae el public_id de una URL o nombre de archivo de Cloudinary.
    """
    import os
    # Si es una URL completa, extraer el nombre del archivo
    base = os.path.basename(file_name_or_url)
    # Quitar extensión si existe
    public_id = os.path.splitext(base)[0]
    return public_id

class CoordenadasField(forms.CharField):
    """Campo personalizado que acepta 'lat, lng' y convierte a GeoJSON"""
    
    def to_python(self, value):
        if not value:
            return None
        
        # Si ya es un diccionario (viene de la BD), devolverlo tal cual
        if isinstance(value, dict):
            return value
        
        # Si es string, parsear "lat, lng"
        if isinstance(value, str):
            try:
                # Extraer números del string (permite diferentes formatos)
                numbers = re.findall(r'-?\d+\.?\d*', value)
                if len(numbers) >= 2:
                    lat = float(numbers[0])
                    lng = float(numbers[1])
                    
                    # Validar rangos
                    if -90 <= lat <= 90 and -180 <= lng <= 180:
                        return {
                            'type': 'Point',
                            'coordinates': [lat, lng]
                        }
                    else:
                        raise forms.ValidationError('Latitud debe estar entre -90 y 90, Longitud entre -180 y 180')
                
            except (ValueError, TypeError):
                pass
        
        raise forms.ValidationError('Formato inválido. Use: "8.049147423101246, -72.25808037610052"')
    
    def prepare_value(self, value):
        """Convierte el GeoJSON a string para mostrarlo en el formulario"""
        if isinstance(value, dict) and value.get('type') == 'Point':
            coordinates = value.get('coordinates', [])
            if len(coordinates) == 2:
                return f"{coordinates[0]}, {coordinates[1]}"
        return value
    
################################Modelo USER-SOCIAL

# Desregistrar el modelo original de social_django
try:
    admin.site.unregister(UserSocialAuth)
except admin.exceptions.NotRegistered:
    pass

class UserSocialAuthProxy(UserSocialAuth):
    class Meta:
        proxy = True
        verbose_name = 'Usuario OAuth2'
        verbose_name_plural = 'Usuarios OAuth2'

@admin.register(UserSocialAuthProxy)
class UserSocialAuthProxyAdmin(admin.ModelAdmin):
    list_display = ('user', 'id', 'provider')
    readonly_fields = ('created', 'modified')
    search_fields = ('user__username', 'provider', 'uid')
    raw_id_fields = ('user',)

    fieldsets = (
        (None, {
            'fields': ('user', 'provider', 'uid', 'extra_data', 'created', 'modified')
        }),
    )

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            user_to_delete = obj.user
            if user_to_delete:
                user_to_delete.delete()
            obj.delete()

################################CLIENTES

class UserCreationForm(forms.ModelForm):
    first_name = forms.CharField(label='Nombre', required=True)
    last_name = forms.CharField(label='Apellido', required=True)
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    banner_imagen = forms.ImageField(label='Imagen de portada', required=False)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)
    make_admin = forms.BooleanField(
        label='Admin',
        required=False,
        help_text='Obtiene todos los permisos de la API y sus usuarios'
    )
    ubicacion_coordenadas = CoordenadasField(
        required=False,
        label='Coordenadas',
        help_text='Formato: "latitud, longitud". Ejemplo: "-16.4897, -68.1193"',
        widget=forms.TextInput(attrs={
            'placeholder': '-16.4897, -68.1193',
            'style': 'width: 300px;'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'is_active', 'make_admin')

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        #  GUARDAR COORDENADAS SI SE PROPORCIONAN
        if 'ubicacion_coordenadas' in self.cleaned_data:
            user.ubicacion_coordenadas = self.cleaned_data['ubicacion_coordenadas']
        # Subir imagen de perfil a Cloudinary (cuenta correcta)
        if 'profile_imagen' in self.cleaned_data and self.cleaned_data['profile_imagen']:
            try:
                upload_result = cloudinary.uploader.upload(
                    self.cleaned_data['profile_imagen'],
                    folder="profile_images/",
                    cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                    api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                    api_secret=settings.CLOUDINARY_STORAGE['API_SECRET']
                )
                # Guardamos la URL completa para incluir versión real
                user.profile_imagen = upload_result.get('secure_url') or upload_result.get('url')
            except Exception as e:
                logger.error(f"Error al subir imagen de perfil a Cloudinary: {e}")
        # Subir imagen de portada/banner
        if 'banner_imagen' in self.cleaned_data and self.cleaned_data['banner_imagen']:
            try:
                upload_result = cloudinary.uploader.upload(
                    self.cleaned_data['banner_imagen'],
                    folder="banner_images/",
                    cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                    api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                    api_secret=settings.CLOUDINARY_BANNER['API_SECRET']
                )
                user.banner_imagen = upload_result.get('secure_url') or upload_result.get('url')
            except Exception as e:
                logger.error(f"Error al subir imagen de portada a Cloudinary: {e}")
        
        if self.cleaned_data['make_admin']:
            user.is_staff = True
            user.is_superuser = True
        
        if commit:
            user.save()
        return user

        
class UserChangeForm(forms.ModelForm):
    first_name = forms.CharField(label='Nombre', required=True)
    last_name = forms.CharField(label='Apellido', required=True)
    banner_imagen = forms.ImageField(label='Imagen de portada', required=False)
    make_admin = forms.BooleanField(
        label='Admin',
        required=False,
        help_text='Obtiene todos los permisos de la API y sus usuarios'
    )
    #  NUEVO CAMPO PARA COORDENADAS
    ubicacion_coordenadas = CoordenadasField(
        required=False,
        label='Coordenadas',
        help_text='Formato: "latitud, longitud". Ejemplo: "-16.4897, -68.1193"',
        widget=forms.TextInput(attrs={
            'placeholder': '-16.4897, -68.1193',
            'style': 'width: 300px;'
        })
    )

    class Meta:
        model = User
        fields = '__all__'

    def clean_password(self):
        """
        Si no se cambia la contraseña, devuelve la que ya tiene el usuario (hash).
        """
        password = self.cleaned_data.get("password")
        if not password:  
            return self.instance.password  # No tocar si no se modificó
        return password  # Devuelve el valor crudo para que save() lo maneje

    def save(self, commit=True):
        user = super().save(commit=False)

        # 🔥 GUARDAR COORDENADAS SI SE PROPORCIONAN
        if 'ubicacion_coordenadas' in self.cleaned_data:
            user.ubicacion_coordenadas = self.cleaned_data['ubicacion_coordenadas']

        # Solo aplicar set_password si el password realmente cambió
        if "password" in self.changed_data:
            user.set_password(self.cleaned_data["password"])

        # ── perfil ──────────────────────────────────────────────────────────────
        # solo tocar si el campo realmente cambió; de lo contrario el simple hecho
        # de guardar otro campo (ej. activar/desactivar is_active) provocaba que
        # Django tratara el FieldFile como "nuevo" y el almacenamiento volviera a
        # subir la misma imagen generando duplicados.
        if 'profile_imagen' in self.changed_data:
            if self.files.get('profile_imagen'):
                try:
                    # borrar anterior
                    if user.profile_imagen:
                        try:
                            cloudinary.uploader.destroy(
                                _extract_public_id(user.profile_imagen.name),
                                cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                                api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                                api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
                            )
                        except Exception as e:
                            logger.error(f"Error al eliminar imagen anterior de Cloudinary: {e}")
                    upload_result = cloudinary.uploader.upload(
                        self.files['profile_imagen'],
                        folder="profile_images/",
                        cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                        api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                        api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
                    )
                    user.profile_imagen = upload_result.get('secure_url') or upload_result.get('url')
                except Exception as e:
                    logger.error(f"Error al subir imagen de perfil a Cloudinary: {e}")
            elif 'profile_imagen-clear' in self.data:
                if user.profile_imagen:
                    try:
                        cloudinary.uploader.destroy(
                            _extract_public_id(user.profile_imagen.name),
                            cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                            api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                            api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
                        )
                    except Exception as e:
                        logger.error(f"Error al eliminar imagen de perfil de Cloudinary: {e}")
                user.profile_imagen = None

        # ── banner/portada ───────────────────────────────────────────────────────
        if 'banner_imagen' in self.changed_data:
            if self.files.get('banner_imagen'):
                try:
                    if user.banner_imagen:
                        try:
                            cloudinary.uploader.destroy(
                                _extract_public_id(user.banner_imagen.name),
                                cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                                api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                                api_secret=settings.CLOUDINARY_BANNER['API_SECRET'],
                            )
                        except Exception as e:
                            logger.error(f"Error al eliminar banner anterior de Cloudinary: {e}")
                    upload_result = cloudinary.uploader.upload(
                        self.files['banner_imagen'],
                        folder="banner_images/",
                        cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                        api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                        api_secret=settings.CLOUDINARY_BANNER['API_SECRET'],
                    )
                    user.banner_imagen = upload_result.get('secure_url') or upload_result.get('url')
                except Exception as e:
                    logger.error(f"Error al subir banner a Cloudinary: {e}")
            elif 'banner_imagen-clear' in self.data:
                if user.banner_imagen:
                    try:
                        cloudinary.uploader.destroy(
                            _extract_public_id(user.banner_imagen.name),
                            cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                            api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                            api_secret=settings.CLOUDINARY_BANNER['API_SECRET'],
                        )
                    except Exception as e:
                        logger.error(f"Error al eliminar banner de Cloudinary: {e}")
                user.banner_imagen = None

        if self.cleaned_data['make_admin']:
            user.is_staff = True
            user.is_superuser = True

        if commit:
            user.save()
        return user

class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    list_display = ('username', 'email', 'is_staff', 'is_active')
    search_fields = ('username', 'email')

    def delete_model(self, request, obj):
        # asegurarnos de pasar por User.delete() que limpia Cloudinary
        obj.delete()

    def delete_queryset(self, request, queryset):
        # el comportamiento por defecto del admin llama a queryset.delete() que
        # no ejecuta User.delete() ni el signal post_delete para cada instancia.
        for obj in queryset:
            obj.delete()

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2')
        }),
        ('Información personal', {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'ubicacion_coordenadas', 'profile_imagen', 'banner_imagen', 'biometric')
        }),
        ('Permisos', {
            'classes': ('wide',),
            'fields': ('is_active', 'make_admin')
        }),
    )

    
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Información personal', {'fields': ('first_name', 'last_name', 'ubicacion_coordenadas', 'profile_imagen', 'banner_imagen', 'biometric')}),
        ('Permisos', {
            'fields': ('is_active', 'make_admin'),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        defaults = {}
        if obj is None:
            defaults['form'] = self.add_form
        else:
            defaults['form'] = self.form
            
        defaults.update(kwargs)
        form = super().get_form(request, obj, **defaults)
        
        if 'make_admin' in form.base_fields:
            form.base_fields['make_admin'].widget.attrs.update({
                'class': 'admin-checkbox',
                'onchange': 'toggleAdminStatus(this)'
            })
            
        return form

    class Media:
        js = ('admin/js/user_admin.js',)



class ClienteAdmin(UserAdmin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model._meta.verbose_name = 'Cliente'
        self.model._meta.verbose_name_plural = 'Clientes'
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(negocio__isnull=True)

    list_display = ('username', 'email', 'date_joined', 'first_name', 'last_name', 'is_active')
    ordering = ('-date_joined',)
    list_filter = ('is_active',)


##########################################negocioS

class MultipleFileInput(Input):
    input_type = 'file'
    needs_multipart_form = True
    template_name = 'django/forms/widgets/file.html'

    def __init__(self, attrs=None):
        default_attrs = {'multiple': True}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def value_from_datadict(self, data, files, name):
        if hasattr(files, 'getlist'):
            return files.getlist(name)
        value = files.get(name)
        if value is None:
            return []
        return [value] if not isinstance(value, list) else value

    def value_omitted_from_data(self, data, files, name):
        return name not in files

class MultipleImageField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # Si no se suben archivos, devolver lista vacía
        if data is None:
            return []
        
        # Si es un solo archivo, convertirlo a lista
        if not isinstance(data, list):
            return [data]
        
        return data


class Negocio(User):
    class Meta:
        proxy = True
        verbose_name = 'Negocio'
        verbose_name_plural = 'Negocios'


class NegocioCreationForm(UserCreationForm):
    first_name = forms.CharField(label='Nombre', required=False)
    last_name = forms.CharField(label='Apellido', required=False)
    # Campos extra que van dentro del JSON
    name_business = forms.CharField(label='Negocio', required=True)
    phone = forms.CharField(label='Teléfono', required=True)
    address = forms.CharField(label='Dirección', required=True)
    city = forms.CharField(label='Ciudad', required=True)
    descripcion = forms.CharField(label='Descripción', widget=forms.Textarea, required=False)
    ubicacion_coordenadas = CoordenadasField(
        required=False,
        label='Coordenadas',
        help_text='Formato: "latitud, longitud". Ejemplo: "-16.4897, -68.1193"',
        widget=forms.TextInput(attrs={
            'placeholder': '-16.4897, -68.1193',
            'style': 'width: 300px;'
        })
    )
    days = forms.MultipleChoiceField(
        label='Días de trabajo',
        choices=[
            ('lunes', 'Lunes'),
            ('martes', 'Martes'),
            ('miercoles', 'Miércoles'),
            ('jueves', 'Jueves'),
            ('viernes', 'Viernes'),
            ('sabado', 'Sábado'),
            ('domingo', 'Domingo')
        ],
        widget=forms.CheckboxSelectMultiple,
        required=True
    )
    
    
    openingTime = forms.TimeField(label='Hora de apertura', widget=forms.TimeInput(attrs={'type': 'time'}),
        required=True)
    closingTime = forms.TimeField(label='Hora de cierre', widget=forms.TimeInput(attrs={'type': 'time'}),
        required=True)
    city = forms.CharField(label='Ciudad', required=False)
    descripcion = forms.CharField(label='Descripción', widget=forms.Textarea, required=False)

    class Meta:
        model = User
        fields = ("email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        # Set username to email
        #user.username = user.email
        
        # 🔥 GUARDAR COORDENADAS SI SE PROPORCIONAN
        if 'ubicacion_coordenadas' in self.cleaned_data:
            user.ubicacion_coordenadas = self.cleaned_data['ubicacion_coordenadas']

        # Manejo de imagen de perfil
        if 'profile_imagen' in self.cleaned_data and self.cleaned_data['profile_imagen']:
            try:
                upload_result = cloudinary.uploader.upload(
                    self.cleaned_data['profile_imagen'],
                    folder="profile_images/",
                    cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                    api_key=settings.CLOUDINARY_STORAGE['API_KEY'],   
                    api_secret=settings.CLOUDINARY_STORAGE['API_SECRET']
                )
                user.profile_imagen = upload_result.get('secure_url') or upload_result.get('url')
            except Exception as e:
                logger.error(f"Error al subir imagen de perfil a Cloudinary: {e}")
        # Manejo de imagen de portada/banner
        if 'banner_imagen' in self.cleaned_data and self.cleaned_data['banner_imagen']:
            try:
                upload_result = cloudinary.uploader.upload(
                    self.cleaned_data['banner_imagen'],
                    folder="banner_images/",
                    cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                    api_key=settings.CLOUDINARY_BANNER['API_KEY'],   
                    api_secret=settings.CLOUDINARY_BANNER['API_SECRET']
                )
                user.banner_imagen = upload_result.get('secure_url') or upload_result.get('url')
            except Exception as e:
                logger.error(f"Error al subir imagen de portada a Cloudinary: {e}")

        # Construcción del JSON embebido
        negocio_data = {
            "name_business": self.cleaned_data.get('name_business'),
            "phone": self.cleaned_data.get('phone'),
            "address": self.cleaned_data.get('address'),
            "city": self.cleaned_data.get('city'),
            "descripcion": self.cleaned_data.get('descripcion'),
            "horario": [{
                "days": self.cleaned_data.get('days', [])
            }],
            "openingTime": self.cleaned_data.get('openingTime').strftime('%H:%M') if self.cleaned_data.get('openingTime') else None,
            "closingTime": self.cleaned_data.get('closingTime').strftime('%H:%M') if self.cleaned_data.get('closingTime') else None
        }

        user.negocio = [negocio_data]

        if commit:
            user.save()
        return user

class NegocioChangeForm(UserChangeForm):
    first_name = forms.CharField(label='Nombre', required=False)
    last_name = forms.CharField(label='Apellido', required=False)
    # Campos extra que van dentro del JSON
    name_business = forms.CharField(label='Negocio', required=True)
    phone = forms.CharField(label='Teléfono', required=True)
    ubicacion_coordenadas = CoordenadasField(
        required=False,
        label='Coordenadas',
        help_text='Formato: "latitud, longitud". Ejemplo: "-16.4897, -68.1193"',
        widget=forms.TextInput(attrs={
            'placeholder': '-16.4897, -68.1193',
            'style': 'width: 300px;'
        })
    )
    address = forms.CharField(label='Dirección', required=True)
    city = forms.CharField(label='Ciudad', required=True)
    descripcion = forms.CharField(label='Descripción', widget=forms.Textarea, required=False)
    days = forms.MultipleChoiceField(
        label='Días de trabajo',
        choices=[
            ('lunes', 'Lunes'),
            ('martes', 'Martes'),
            ('miercoles', 'Miércoles'),
            ('jueves', 'Jueves'),
            ('viernes', 'Viernes'),
            ('sabado', 'Sabado'),
            ('domingo', 'Domingo')
        ],
        widget=forms.CheckboxSelectMultiple,
        required=True
    )
    openingTime = forms.TimeField(
        label='Hora de apertura', 
        widget=forms.TimeInput(attrs={'type': 'time'}),
        required=True
    )
    closingTime = forms.TimeField(
        label='Hora de cierre', 
        widget=forms.TimeInput(attrs={'type': 'time'}),
        required=True
    )
    city = forms.CharField(label='Ciudad', required=False)
    descripcion = forms.CharField(label='Descripción', widget=forms.Textarea, required=False)

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.negocio and len(self.instance.negocio) > 0:
            negocio_data = self.instance.negocio[0]
            self.fields['name_business'].initial = negocio_data.get('name_business', '')
            self.fields['phone'].initial = negocio_data.get('phone', '')
            self.fields['address'].initial = negocio_data.get('address', '')
            self.fields['city'].initial = negocio_data.get('city', '')
            self.fields['descripcion'].initial = negocio_data.get('descripcion', '')

            # Horario
            if 'horario' in negocio_data and len(negocio_data['horario']) > 0:
                horario = negocio_data['horario'][0]
                self.fields['days'].initial = horario.get('days', [])
                self.fields['openingTime'].initial = negocio_data.get('openingTime', '')
                self.fields['closingTime'].initial = negocio_data.get('closingTime', '')

            # Imagen de perfil
            if self.instance and self.instance.profile_imagen:
                try:
                    profile_url, _ = cloudinary.utils.cloudinary_url(
                        self.instance.profile_imagen.name,
                        cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                        api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                        api_secret=settings.CLOUDINARY_STORAGE['API_SECRET']
                    )
                    self.fields['profile_imagen'].help_text = mark_safe(
                        f'<strong>Imagen actual:</strong><br>'
                        f'<img src="{profile_url}" height="100" style="border-radius: 50%;"><br>'
                        f'<span style="color: green;">Dejar vacío para mantener la imagen actual</span>'
                    )
                    self.fields['profile_imagen'].required = False
                except Exception as e:
                    logger.error(f"Error al generar URL de imagen de perfil: {e}")
                    self.fields['profile_imagen'].help_text = "Error al cargar la imagen actual"
            # Imagen de portada/banner
            if self.instance and self.instance.banner_imagen:
                try:
                    banner_url, _ = cloudinary.utils.cloudinary_url(
                        self.instance.banner_imagen.name,
                        cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                        api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                        api_secret=settings.CLOUDINARY_BANNER['API_SECRET']
                    )
                    self.fields['banner_imagen'].help_text = mark_safe(
                        f'<strong>Portada actual:</strong><br>'
                        f'<img src="{banner_url}" height="100" style="display:block;margin-bottom:5px;"><br>'
                        f'<span style="color: green;">Dejar vacío para mantener la portada actual</span>'
                    )
                    self.fields['banner_imagen'].required = False
                except Exception as e:
                    logger.error(f"Error al generar URL de imagen de portada: {e}")
                    self.fields['banner_imagen'].help_text = "Error al cargar la portada actual"
    def save(self, commit=True):
        user = super().save(commit=False)

        # Set username to email if not set
        #if not user.username:
        #    user.username = user.email

        # 🔥 GUARDAR COORDENADAS SI SE PROPORCIONAN
        if 'ubicacion_coordenadas' in self.cleaned_data:
            user.ubicacion_coordenadas = self.cleaned_data['ubicacion_coordenadas']

        
        # 1. Lógica para la imagen de perfil
        # Aseguramos que solo entramos en este bloque si el campo de imagen fue tocado
        # Y tiene un archivo válido.
        # Usa `self.cleaned_data.get('profile_imagen')` directamente como condición
        # para manejar el caso de que no haya archivo subido.
        if 'profile_imagen' in self.changed_data:
            new_image = self.cleaned_data.get('profile_imagen')
        
            if new_image:
                # 1. Si hay nueva imagen => borrar la anterior y subir la nueva
                if user.profile_imagen:
                    try:
                        cloudinary.uploader.destroy(
                            _extract_public_id(user.profile_imagen.name),
                            cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                            api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                            api_secret=settings.CLOUDINARY_STORAGE['API_SECRET']
                        )
                    except Exception as e:
                        logger.error(f"Error al eliminar imagen anterior de Cloudinary: {e}")
        
                try:
                    upload_result = cloudinary.uploader.upload(
                        new_image,
                        folder="profile_images/",
                        cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                        api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                        api_secret=settings.CLOUDINARY_STORAGE['API_SECRET']
                    )
                    user.profile_imagen = upload_result.get('secure_url') or upload_result.get('url')
                except Exception as e:
                    logger.error(f"Error al subir imagen de perfil a Cloudinary: {e}")
                    # 👇 NO lanzamos ValidationError, solo logueamos
                    return user  
        
            else:
                # 2. Si el usuario limpió la imagen (checkbox clear en admin)
                if user.profile_imagen:
                    try:
                        cloudinary.uploader.destroy(
                            _extract_public_id(user.profile_imagen.name),
                            cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                            api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                            api_secret=settings.CLOUDINARY_STORAGE['API_SECRET']
                        )
                    except Exception as e:
                        logger.error(f"Error al eliminar imagen de perfil de Cloudinary: {e}")
                user.profile_imagen = None  # o '' dependiendo de tu modelo
        # 2. Lógica para imagen de portada/banner (idéntica a la anterior)
        if 'banner_imagen' in self.changed_data:
            new_banner = self.cleaned_data.get('banner_imagen')

            if new_banner:
                if user.banner_imagen:
                    try:
                        cloudinary.uploader.destroy(
                            _extract_public_id(user.banner_imagen.name),
                            cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                            api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                            api_secret=settings.CLOUDINARY_BANNER['API_SECRET']
                        )
                    except Exception as e:
                        logger.error(f"Error al eliminar banner anterior de Cloudinary: {e}")
                try:
                    upload_result = cloudinary.uploader.upload(
                        new_banner,
                        folder="banner_images/",
                        cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                        api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                        api_secret=settings.CLOUDINARY_BANNER['API_SECRET']
                    )
                    user.banner_imagen = upload_result.get('secure_url') or upload_result.get('url')
                except Exception as e:
                    logger.error(f"Error al subir banner a Cloudinary: {e}")
                    return user
            else:
                if user.banner_imagen:
                    try:
                        cloudinary.uploader.destroy(
                            _extract_public_id(user.banner_imagen.name),
                            cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                            api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                            api_secret=settings.CLOUDINARY_BANNER['API_SECRET']
                        )
                    except Exception as e:
                        logger.error(f"Error al eliminar banner de Cloudinary: {e}")
                user.banner_imagen = None  # limpiar si se desmarcó

        # 3. Construir el JSON del campo 'negocio'
        negocio_data = {
            "name_business": self.cleaned_data.get('name_business'),
            "phone": self.cleaned_data.get('phone'),
            "address": self.cleaned_data.get('address'),
            "city": self.cleaned_data.get('city'),
            "descripcion": self.cleaned_data.get('descripcion'),
            "horario": [{
                "days": self.cleaned_data.get('days', [])
            }],
            "openingTime": self.cleaned_data.get('openingTime').strftime('%H:%M') if self.cleaned_data.get('openingTime') else None,
            "closingTime": self.cleaned_data.get('closingTime').strftime('%H:%M') if self.cleaned_data.get('closingTime') else None
        }

        user.negocio = [negocio_data]

        if commit:
            user.save()
        return user
@admin.register(Negocio)
class NegocioAdmin(UserAdmin):
    form = NegocioChangeForm
    add_form = NegocioCreationForm

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'profile_imagen', 'banner_imagen', 'ubicacion_coordenadas', 'biometric'),
        }),
        ('Información del negocio', {
            'fields': ('name_business', 'phone', 'address', 'city', 'descripcion'),
        }),
        ('Horario', {
            'fields': ('days', 'openingTime', 'closingTime'),
        }),
        ('Estado de la negocio', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
        }),
    )

    fieldsets = (
        (None, {'fields': ('password',)}),
        ('Información personal', {'fields': ('email', 'profile_imagen', 'banner_imagen', 'ubicacion_coordenadas', 'biometric')}),
        ('Información de el negocio', {
            'fields': ('name_business', 'phone', 'address', 'city', 'descripcion', 'get_rating'),
        }),
        ('Horario', {
            'fields': ('days', 'openingTime', 'closingTime'),
        }),
        ('Estado de la negocio', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
        }),
    )


    list_display = ( 'get_name_business', 'get_city', 'email', 'get_dias','date_joined','get_rating', 'is_active')
    ordering = ('-date_joined',)


    readonly_fields = ('get_rating',)  # ¡Ahora sí funciona porque es un método!
    # Método para obtener el rating
    def get_rating(self, obj):
        if obj.negocio and isinstance(obj.negocio, list) and len(obj.negocio) > 0:
            return obj.negocio[0].get('rating', '0')
        return '0'
    get_rating.short_description = 'Rating' 

    def get_name_business(self, obj):
        return obj.negocio[0].get('name_business', '') if obj.negocio else ''
    get_name_business.short_description = 'negocio'

    def get_city(self, obj):
        # extraer ciudad desde el JSON del negocio
        if obj.negocio and isinstance(obj.negocio, list) and len(obj.negocio) > 0:
            return obj.negocio[0].get('city', '')
        return ''
    get_city.short_description = 'Ciudad'

    # Horario (días + apertura + cierre)
    def get_horario(self, obj):
        if obj.negocio and isinstance(obj.negocio, list) and len(obj.negocio) > 0:
            dias = obj.negocio[0].get('days', [])
            opening = obj.negocio[0].get('openingTime', '')
            closing = obj.negocio[0].get('closingTime', '')
            return f"{', '.join(dias)} ({opening} - {closing})"
        return ''
    get_horario.short_description = 'Horario'

    def get_dias(self, obj):
        if obj.negocio and isinstance(obj.negocio, list) and len(obj.negocio) > 0:
            horario = obj.negocio[0].get('horario', [])
            dias = horario[0].get('days', []) if horario else []
            return ', '.join(dias) if dias else 'Sin días'
        return ''
    get_dias.short_description = 'Días de trabajo'


    def get_phone(self, obj):
        return obj.negocio[0].get('phone', '') if obj.negocio else ''
    get_phone.short_description = 'Teléfono'

    def get_queryset(self, request):
        return super().get_queryset(request).filter(negocio__isnull=False)
    

class MultipleFileInput(Input):
    input_type = 'file'
    needs_multipart_form = True
    template_name = 'django/forms/widgets/file.html'

    def __init__(self, attrs=None):
        default_attrs = {'multiple': True}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def value_from_datadict(self, data, files, name):
        if hasattr(files, 'getlist'):
            return files.getlist(name)
        value = files.get(name)
        if value is None:
            return []
        return [value] if not isinstance(value, list) else value

    def value_omitted_from_data(self, data, files, name):
        return name not in files

class MultipleImageField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # Si no se suben archivos, devolver lista vacía
        if data is None:
            return []
        
        # Si es un solo archivo, convertirlo a lista
        if not isinstance(data, list):
            return [data]
        
        return data
    
class ServicioForm(forms.ModelForm):
    imagenes = MultipleImageField(label='Imagenes del servicio', required=False)

    mostrar_imagenes = forms.CharField(
        required=False,
        widget=forms.HiddenInput()  # se usa solo para mostrar en el admin
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Mostrar imágenes actuales (como tu ejemplo)
        if self.instance and self.instance.pk and self.instance.imagen_urls:
            try:
                images_html = "<strong>Imágenes actuales:</strong><br>"
                for entry in self.instance.imagen_urls:
                    # si ya tenemos URL completa, úsala tal cual
                    if isinstance(entry, str) and entry.startswith(('http://','https://')):
                        imagen_url = entry
                    else:
                        imagen_url, _ = cloudinary.utils.cloudinary_url(
                            entry,
                            cloud_name=settings.SERVICIOS_CLOUDINARY["CLOUD_NAME"],
                            api_key=settings.SERVICIOS_CLOUDINARY["API_KEY"],
                            api_secret=settings.SERVICIOS_CLOUDINARY["API_SECRET"]
                        )
                    images_html += f'<img src="{imagen_url}" height="150" style="margin:5px;border-radius:10px;">'

                images_html += (
                    "<br><span style='color: green;'>"
                    "Dejar vacío para mantener las imágenes actuales o subir nuevas para reemplazarlas."
                    "</span>"
                )

                self.fields["imagenes"].help_text = mark_safe(images_html)
                self.fields["imagenes"].required = False

            except Exception as e:
                logger.error(f"Error al generar URLs de imágenes: {e}")
                self.fields["imagenes"].help_text = "Error al cargar las imágenes actuales"


    class Meta:
        model = Servicio
        fields = ["negocio", "description", "precio", "moneda", "imagenes"]  # 👈 corregido

    def save(self, commit=True):
        instance = super().save(commit=False)
    
        imagenes = self.files.getlist("imagenes")  # capturamos varias imágenes
        public_ids = []
    
        if imagenes:
            if len(imagenes) > 4:
                raise forms.ValidationError("Solo puedes subir un máximo de 4 imágenes.")
    
            # 🔹 Eliminar imágenes antiguas (extraer public_id de la URL si
            # es necesario)
            if instance.imagen_urls:
                from .serializers import _extract_public_id as _extract
                for old_entry in instance.imagen_urls:
                    public_id = _extract(old_entry)
                    try:
                        cloudinary.uploader.destroy(
                            public_id,
                            cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                            api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                            api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
                        )
                    except Exception as e:
                        logger.error(f"No se pudo borrar la imagen antigua {old_entry}: {e}")
    
            # 🔹 Subir nuevas imágenes
            for imagen in imagenes:
                upload_result = cloudinary.uploader.upload(
                    imagen,
                    folder="services_images/",
                    cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                    api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                    api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
                )
                # almacenar la URL segura para simplificar lecturas futuras
                public_ids.append(upload_result.get('secure_url') or upload_result.get('url'))
            # asignar nuevas URLs al campo
            instance.imagen_urls = public_ids

        if commit:
            instance.save()
        return instance

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("cliente", "negocio", "description", "date", "rating")
    list_filter = ("cliente", "negocio")
    search_fields = ("description", "negocio__username")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Limita la selección de cliente a usuarios sin negocio (es decir, clientes)
        if db_field.name == 'cliente':
            kwargs['queryset'] = User.objects.filter(negocio__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    form = ServicioForm
    list_display = ("titulo", "description", "negocio", "precio", "moneda")
    list_filter = ("moneda", "negocio")
    search_fields = ("description", "negocio__username")
    ordering = ("-id",)

    def delete_model(self, request, obj):
        # Asegurarse de que el post_delete signal procese correctamente
        obj.delete()

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()
    

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'emisor_info',
        'receptor_info',
        'mensaje_texto_short',
        'visto',
        'hora_mensaje',
    )
    list_filter = ('visto', 'hora_mensaje')
    search_fields = (
        'mensaje_texto',
        'emisor__email',
        'emisor__username',
        'receptor__email',
        'receptor__username',
    )
    readonly_fields = ('emisor', 'receptor', 'hora_mensaje')
    raw_id_fields = ('emisor', 'receptor')
    ordering = ('-hora_mensaje',)
    date_hierarchy = 'hora_mensaje'
    list_per_page = 40
    fieldsets = (
        (None, {
            'fields': ('emisor', 'receptor', 'mensaje_texto', 'visto', 'hora_mensaje')
        }),
    )

    def emisor_info(self, obj):
        if not obj.emisor:
            return '-'
        if obj.emisor.negocio:
            business_name = obj.emisor.negocio[0].get('name_business') if isinstance(obj.emisor.negocio, (list, tuple)) and obj.emisor.negocio else ''
            return f"{business_name or obj.emisor.username or obj.emisor.email} ({obj.emisor.email})"
        return f"{obj.emisor.username or obj.emisor.email} ({obj.emisor.email})"
    emisor_info.short_description = 'Emisor'

    def receptor_info(self, obj):
        if not obj.receptor:
            return '-'
        if obj.receptor.negocio:
            business_name = obj.receptor.negocio[0].get('name_business') if isinstance(obj.receptor.negocio, (list, tuple)) and obj.receptor.negocio else ''
            return f"{business_name or obj.receptor.username or obj.receptor.email} ({obj.receptor.email})"
        return f"{obj.receptor.username or obj.receptor.email} ({obj.receptor.email})"
    receptor_info.short_description = 'Receptor'

    def mensaje_texto_short(self, obj):
        if not obj.mensaje_texto:
            return '-'
        return obj.mensaje_texto[:80] + ('...' if len(obj.mensaje_texto) > 80 else '')
    mensaje_texto_short.short_description = 'Mensaje'


admin.site.unregister(Group)
# Registro final de modelos
admin.site.register(User, UserAdmin)  # Registro temporal
admin.site.unregister(User)  # Desregistramos para registrar las versiones personalizadas
admin.site.register(User, ClienteAdmin)  # Registra solo clientes
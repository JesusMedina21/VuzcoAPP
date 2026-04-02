import cloudinary
from rest_framework import serializers
from .models import *
from datetime import datetime, time
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db.models import Avg 
User = get_user_model() # Obtén el modelo de usuario actual
from rest_framework import serializers
from django.core.validators import MinLengthValidator
from rest_framework.exceptions import ValidationError
from djoser import utils
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str, force_bytes
import phonenumbers
from phonenumbers.phonenumberutil import NumberParseException
from decouple import config
import tempfile, os
from .nsfw_detector import *
# Geocoding inverso
from functools import lru_cache

# Geopy es opcional en entornos donde no esté instalado (docs/schema local)
try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter

    # Inicializar geolocator y rate limiter
    geolocator = Nominatim(user_agent="Vuzco_geocoder")
    reverse = RateLimiter(geolocator.reverse, min_delay_seconds=1, max_retries=2)
    GEOPY_AVAILABLE = True
except Exception:
    GEOPY_AVAILABLE = False
    reverse = None


def _coords_to_lat_lon(coords):
    """Normaliza una tupla/lista de coordenadas a (lat, lon).
    Maneja entradas que pueden venir como [lat, lon] o [lon, lat].
    """


def _extract_public_id(value):
    """Extrae el *public_id* de un valor que puede ser:

    * un public_id ya limpio (`profile_images/abc123`)
    * una URL completa (`https://.../upload/v1773/.../abc123.jpg`)
    * un objeto Django `ImageFieldFile` (se convierte a cadena)

    Se devuelve un string sin versión ni extensión, adecuado para pasar a
    ``cloudinary.uploader.destroy()``.
    """
    if not value:
        return value

    # siempre trabajar con texto para evitar errores de tipo
    val = str(value)

    # si ya parece un public_id normal, regresarlo
    if not val.startswith("http"):
        return val

    import re
    m = re.search(r"/upload/(?:v\d+/)?(.+?)(?:\.[^./]+)?$", val)
    if m:
        return m.group(1)
    # fallback al texto completo
    return val

    try:
        a, b = coords
    except Exception:
        return None

    # Caso 1: [lat, lon]
    if -90 <= float(a) <= 90 and -180 <= float(b) <= 180:
        return float(a), float(b)
    # Caso 2: [lon, lat]
    if -90 <= float(b) <= 90 and -180 <= float(a) <= 180:
        return float(b), float(a)
    return None


@lru_cache(maxsize=1024)
def reverse_geocode_ciudad_coordenadas(lat, lon):
    """Devuelve el nombre de la ciudad (en español si es posible) para lat/lon.
    Resultado cacheado en memoria para reducir llamadas externas.
    """
    if not GEOPY_AVAILABLE:
        return None
    try:
        location = reverse((lat, lon), language="es")
        if not location:
            return None
        addr = location.raw.get("address", {})
        return (
            addr.get("ciudad_coordenadas") or addr.get("town") or addr.get("village") or
            addr.get("municipality") or addr.get("county") or addr.get("state")
        )
    except Exception:
        return None
#from nsfw_detector import predict
# Diccionario para mapear nombres de días a números de semana de Python (lunes=0, domingo=6)
DAYS_OF_WEEK_MAP = {
    'lunes': 0,
    'martes': 1,
    'miercoles': 2,
    'jueves': 3,
    'viernes': 4,
    'sabado': 5,
    'domingo': 6,
}

#####################VALIDAR COORDENADAS

class CoordenadasField(serializers.JSONField):
    def to_internal_value(self, data):
        # Validar formato de coordenadas
        if isinstance(data, dict) and data.get('type') == 'Point':
            coordinates = data.get('coordinates', [])
            if len(coordinates) == 2:
                lat, lng = coordinates
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return data
        
        raise serializers.ValidationError(
            'Formato de coordenadas inválido. Use: {"type": "Point", "coordinates": [lat, lng]}'
        )


def _is_business_user(user):
    if user is None:
        return False
    negocio = getattr(user, 'negocio', None)
    if not negocio:
        return False
    if isinstance(negocio, (list, tuple)):
        return bool(negocio)
    if isinstance(negocio, dict):
        return bool(negocio)
    return False


def _get_business_name(user):
    negocio = getattr(user, 'negocio', None)
    if isinstance(negocio, (list, tuple)) and negocio:
        first = negocio[0] if len(negocio) > 0 else {}
        return first.get('name_business')
    if isinstance(negocio, dict):
        return negocio.get('name_business')
    return None


def _serialize_chat_user(user):
    if user is None:
        return None
    data = {
        'id': str(user.id),
        'email': str(user.email) if getattr(user, 'email', None) else None,
    }
    if _is_business_user(user):
        data['name_business'] = _get_business_name(user) or ''
    else:
        data['username'] = str(user.username) if getattr(user, 'username', None) else ''
    return data


class ObjectIdRelatedField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        if value is None:
            return None

        if hasattr(value, 'id') and hasattr(value, 'email'):
            return _serialize_chat_user(value)

        raw_pk = getattr(value, 'pk', None) or getattr(value, 'id', None) or str(value)
        try:
            user = User.objects.filter(pk=raw_pk).first()
            if user:
                return _serialize_chat_user(user)
        except Exception:
            pass

        return str(raw_pk)


class ChatMessageSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    emisor = serializers.SerializerMethodField()
    receptor = ObjectIdRelatedField(queryset=User.objects.all())
    visto = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'emisor', 'receptor', 'mensaje_texto', 'hora_mensaje', 'visto']
        read_only_fields = ['id', 'hora_mensaje', 'emisor', 'visto']

    def get_id(self, obj):
        return str(obj.id) if obj.id else None

    def get_emisor(self, obj):
        return _serialize_chat_user(obj.emisor)

    def get_visto(self, obj):
        request = self.context.get('request')
        if request and getattr(request, 'user', None) == obj.emisor:
            return obj.visto
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and getattr(request, 'user', None) == instance.receptor:
            data.pop('visto', None)
        return data

    def validate(self, attrs):
        request = self.context.get('request')
        sender = getattr(request, 'user', None) if request else None
        receptor = attrs.get('receptor')

        if sender and receptor and sender == receptor:
            raise serializers.ValidationError('No se puede enviar un mensaje a sí mismo.')

        if sender and receptor:
            if not _is_business_user(sender) and not _is_business_user(receptor):
                raise serializers.ValidationError(
                    'Los clientes no pueden enviarse mensajes entre sí. Solo se permiten conversaciones cliente<->negocio y negocio<->negocio.'
                )

        return attrs

    def validate_receptor(self, value):
        request = self.context.get('request')
        if not value:
            raise serializers.ValidationError('El campo receptor es obligatorio.')
        if not value.is_active:
            raise serializers.ValidationError('No se puede enviar mensajes a usuarios inactivos.')
        return value

###############################################AUTH

class UserCreateSerializer(serializers.ModelSerializer):
    negocio = serializers.JSONField(required=False)
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'password', 'first_name', 'last_name', 'biometric', 'negocio']
        extra_kwargs = {
            'password': {'write_only': True},
            'biometric': {'write_only': True},
        }
    def to_representation(self, instance):
       rep = super().to_representation(instance)
       rep['id'] = str(rep['id'])  # Asegúrate de que el id sea una cadena
       return rep
    def create(self, validated_data):
        negocio_data = validated_data.pop('negocio', None)
        user = User(**validated_data)
        user.set_password(validated_data['password'])
        user.save()
        if negocio_data:
            user.negocio = negocio_data
            user.save()
        return user

class ConfirmarEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_email = serializers.EmailField()

    default_error_messages = {
        "invalid_token": "Token inválido o expirado",
        "invalid_uid": "Usuario inválido",
    }

    def validate(self, attrs):
        try:
            uid = utils.decode_uid(attrs["uid"])
            self.user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError({"uid": self.default_error_messages["invalid_uid"]})

        return attrs
    
class ActivarEmailSerializer(serializers.Serializer):
    """Serializer utilizado para activar cuentas (o ampliar en el futuro para
    validar enlaces de confirmación de email).

    Solo comprueba que el UID y el token decodifiquen a un usuario válido y que
    el token sea correcto. No requiere ningún campo adicional.
    """
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            self.user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError({"uid": "ID de usuario inválido"})

        if not default_token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({"token": "Token inválido o expirado"})

        return attrs
class ActivarNuevoEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            self.user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError({"uid": "ID de usuario inválido"})

        if not default_token_generator.check_token(self.user, attrs['token']):
            raise serializers.ValidationError({"token": "Token inválido o expirado"})

        if not self.user.pending_email:
            raise serializers.ValidationError({"detail": "No hay cambio de email pendiente"})

        return attrs
    
class ClienteSerializer(serializers.ModelSerializer):
    ciudad_coordenadas = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    email = serializers.EmailField(required=True) 
    profile_imagen = serializers.ImageField(  # Cambia a ImageField
        required=False,
        allow_null=True,
    )
    ubicacion_coordenadas = CoordenadasField(  # ← Campo validado
        required=False, 
        allow_null=True,
        help_text='Coordenadas en formato: {"type": "Point", "coordinates": [lat, lng]}'
    )

    class Meta:
        model = User
        fields = ['id',  'first_name', 'last_name', 'username', 'email', 'password', 'profile_imagen', 'ubicacion_coordenadas', 'biometric', 'ciudad_coordenadas']
        extra_kwargs = {
            'password': {'write_only': True},
            'biometric': {'write_only': True},
            'email': {'read_only': False}  # Permitimos escritura inicial
        }

    def get_id(self, obj):
        return str(obj.id) if obj.id else None
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # convertimos la imagen si existe utilizando el helper global,
        # evitando así depender de ``.url`` y del estado de ``cloudinary.config``.
        try:
            if instance.profile_imagen:
                rep['profile_imagen'] = build_cloudinary_url(
                    instance.profile_imagen.name,
                    banner=False
                )
        except Exception:
            pass

        # (ID-hiding logic omitted for brevity; el foco aquí es la URL de la imagen)
        return {key: value for key, value in rep.items() if value is not None}

    def get_ciudad_coordenadas(self, obj):
        # Preferir valor persistido si existe
        if getattr(obj, 'ciudad_coordenadas', None):
            return obj.ciudad_coordenadas

        point = getattr(obj, 'ubicacion_coordenadas', None)
        if not point:
            return None

        # extraer coords desde dict o GEOS
        coords = None
        if isinstance(point, dict):
            coords = point.get('coordinates', [])
        elif hasattr(point, 'coords'):
            # GeoDjango Point: (x, y)
            coords = [point.x, point.y]

        if not coords or len(coords) != 2:
            return None

        parsed = _coords_to_lat_lon(coords)
        if not parsed:
            return None
        lat, lon = parsed
        lat = round(float(lat), 5)
        lon = round(float(lon), 5)
        ciudad = reverse_geocode_ciudad_coordenadas(lat, lon)
        if ciudad:
            try:
                obj.ciudad_coordenadas = ciudad
                obj.save(update_fields=['ciudad_coordenadas'])
            except Exception:
                pass
        return ciudad

    def validate(self, data):
        # Validación de email único antes de procesar la imagen
        email = data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError({
                "email": "Ya existe un usuario con este email."
            })
        
        # Validación de username único si es necesario
        username = data.get('username')
        if username and User.objects.filter(username=username).exists():
            raise serializers.ValidationError({
                "username": "Ya existe un usuario con este username."
            })
        
        # Resto de tus validaciones existentes
        if self.instance and 'email' in self.initial_data:
            if self.initial_data['email'] != self.instance.email:
                raise serializers.ValidationError({
                    "email": "El email no puede ser modificado."
                })
        
        expected_input_fields = {'username', 'profile_imagen', 'first_name', 'last_name', 'ubicacion_coordenadas', 'email', 'password', 'biometric'}
        initial_keys = set(self.initial_data.keys())
        extra_fields = initial_keys - expected_input_fields
        
        if extra_fields:
            raise serializers.ValidationError(
                f"Campos no permitidos para clientes: {', '.join(sorted(list(extra_fields)))}"
            )
        
        return data

    def create(self, validated_data):
    
        # Extraer la imagen de perfil
        profile_imagen_file = validated_data.pop('profile_imagen', None)
        profile_imagen_public_id = None
        
        # Subir imagen a Cloudinary si existe
        if profile_imagen_file:
            # Configurar Cloudinary para cuenta principal
            cloudinary.config(
                cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
            )
            
            # Subir imagen a la carpeta profile_images
            upload_result = cloudinary.uploader.upload(
                profile_imagen_file,
                folder="profile_images/",  # Aquí especificas la carpeta
                resource_type="image"
            )
            # Guardar URL completa (incluye versión correcta)
            profile_imagen_public_id = (
                upload_result.get('secure_url') or upload_result.get('url')
            )
            print(f"Imagen de perfil subida a: {profile_imagen_public_id}")
        
        # Crear usuario con la URL de la imagen (o None si no se subió)
        user = User(**validated_data)
        user.set_password(validated_data['password'])
        user.is_active = False
        user.profile_imagen = profile_imagen_public_id  # Guardar URL o None
        
        try:
            user.save()
            return user
        except Exception as e:
            # Si hay error al guardar, eliminar la imagen subida
            if profile_imagen_public_id:
                try:
                    cloudinary.uploader.destroy(profile_imagen_public_id)
                    print(f"Imagen revertida debido a error: {profile_imagen_public_id}")
                except Exception as delete_error:
                    print(f"Error al eliminar imagen: {delete_error}")
            raise e
    def update(self, instance, validated_data):
        
        # Extraer la nueva imagen de perfil si existe
        profile_imagen_file = validated_data.pop('profile_imagen', None)
        old_profile_imagen = instance.profile_imagen
        
        # Procesar nueva imagen si se proporciona
        if profile_imagen_file:
            # Configurar Cloudinary
            cloudinary.config(
                cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
            )
            
            # Subir nueva imagen
            upload_result = cloudinary.uploader.upload(
                profile_imagen_file,
                folder="profile_images/",
                resource_type="image"
            )
            
            # Guardar URL completa (no sólo public_id)
            validated_data['profile_imagen'] = (
                upload_result.get('secure_url') or upload_result.get('url')
            )
            
            # Eliminar imagen anterior si existe
            if old_profile_imagen:
                try:
                    cloudinary.uploader.destroy(old_profile_imagen)
                    print(f"Imagen anterior eliminada: {old_profile_imagen}")
                except Exception as delete_error:
                    print(f"Error al eliminar imagen anterior: {delete_error}")
        
        # Resto del código de update...
        old_username = instance.username
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
    
        instance.save()
        return instance

#########################################################33#Serializadores para la negocio 


class HorarioSerializer(serializers.Serializer):
    days = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo'
        ]),
        required=True
    )

    def to_representation(self, instance):
        return [
            {"days": instance['days']}
        ]

    def to_internal_value(self, data):
        if isinstance(data, list):
            internal_data = {}
            for item in data:
                if isinstance(item, dict):
                    if 'days' in item:
                        days = item['days']
                        internal_data['days'] = [days] if isinstance(days, str) else days
            return internal_data
        return super().to_internal_value(data)

class TimeFieldToString(serializers.Field):
    def to_representation(self, value):
        """Convierte time a string (ej: "16:30")"""
        if isinstance(value, str):
            return value  # Ya está en formato string
        return value.strftime('%H:%M') if value else None

    def to_internal_value(self, data):
        """Convierte string a objeto time, pero luego lo mantiene como string para MongoDB"""
        try:
            if isinstance(data, time):
                return data.strftime('%H:%M')  # Convertir time a string inmediatamente
            
            if isinstance(data, str):
                # Elimina espacios y la 'Z' final si existe
                clean_data = data.strip().rstrip('Z')
                
                # Intenta con diferentes formatos
                for time_format in ['%H:%M', '%H:%M:%S', '%H:%M:%S.%f']:
                    try:
                        time_obj = datetime.strptime(clean_data, time_format).time()
                        return time_obj.strftime('%H:%M')  # Convertir a string
                    except ValueError:
                        continue
                
            raise ValueError
        except (ValueError, TypeError):
            raise serializers.ValidationError(
                "Formato de hora inválido. Use HH:MM, HH:MM:SS o HH:MM:SS.sss"
            )
        

# helper type used when serializing nested `negocio` dictionaries; it avoids
# KeyError when a field is absent by returning `None` instead of raising.
class SafeDict(dict):
    def __getitem__(self, key):
        return dict.get(self, key, None)


class negocioProfileSerializer(serializers.Serializer):
    name_business = serializers.CharField(
        required=True,
        min_length=4,
        validators=[MinLengthValidator(4)],
        error_messages={
            'min_length': 'El nombre del negocio debe tener al menos 4 caracteres.'
        }
    )
    city = serializers.CharField(required=True)
    # estos campos pueden faltar en algunos documentos antiguos, así que no los
    # marcamos como "required" para que la serialización de lectura no falle.
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    #services = ServicionegocioSerializer(many=True, required=True)
    horario = HorarioSerializer(many=True, required=True)
    openingTime = TimeFieldToString(required=True)
    closingTime = TimeFieldToString(required=True)
    rating = serializers.SerializerMethodField(read_only=True)

    def validate(self, data):
        # Obtener los valores existentes si estamos en una actualización
        existing_opening = None
        existing_closing = None
        
        if self.instance:
            existing_opening = self.instance.get('openingTime')
            existing_closing = self.instance.get('closingTime')
        
        # Obtener nuevos valores o usar los existentes
        opening_time = data.get('openingTime', existing_opening)
        closing_time = data.get('closingTime', existing_closing)
        
        # Solo validar si ambos tiempos están disponibles
        if opening_time is not None and closing_time is not None:
            if opening_time == closing_time:
                raise serializers.ValidationError({
                    'openingTime': 'El horario de apertura no puede ser igual al horario de cierre.'
                })
        
        return data

    def validate_horario(self, value):
        """
        Valida que el campo 'horario' tenga la estructura correcta
        """
        if not value:
            raise serializers.ValidationError("El campo 'horario' no puede estar vacío.")
        
        # AGREGAR ESTA VALIDACIÓN para asegurar que solo haya un objeto en la lista
        if len(value) > 1:
            raise serializers.ValidationError("El campo 'horario' no puede tener más de un objeto. Un solo objeto debe contener todos los días.")

        
        has_days = False
        
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    if 'days' in item:
                        if item['days']:  # Verifica que no esté vacío
                            has_days = True
        
        if not has_days:
            raise serializers.ValidationError("Debe especificar al menos un día en el horario.")
        
        return value

    def get_rating(self, obj):
        # obj en este punto es el diccionario del perfil del negocio, no la instancia de User
        # Necesitamos el ID del usuario (el negocio) para buscar los comentarios.
        # Esto requerirá pasar el ID del usuario desde negocioSerializer.
        
        # Una forma más robusta es pasar el user_id al contexto del negocioProfileSerializer
        # O calcularlo en negocioSerializer y luego pasarlo al to_representation.
        # Por ahora, asumamos que obj es el objeto de User, no solo el dict de negocio.
        # Si obj es el dict, necesitarás el ID del usuario.
        
        # Si 'obj' es una instancia de User (como cuando es llamado desde negocioSerializer.to_representation)
        if isinstance(obj, User):
            negocio_user_id = obj.id
        # Si 'obj' es el diccionario 'negocio' del JSONField, y necesitas el ID del User padre
        else: # Esto es más probable si se llama desde dentro de negocioSerializer.to_representation
            # Accede al ID de la instancia de User que contiene este perfil del negocio
            # Esto asume que negocioSerializer pasa 'instance' a este serializador, lo cual es estándar.
            negocio_user_id = self.context.get('user_id_for_rating') # Necesitamos pasar este en el context
            if not negocio_user_id:
                return None # O lanzar un error si es un dato esencial

        # Busca los comentarios en la nueva colección Comment
        comments = Comment.objects.filter(negocio_id=negocio_user_id)
        if not comments.exists():
            return None
        
        total_rating = sum(c.rating for c in comments)
        return round(total_rating / comments.count(), 1)
    
    def validate_phone(self, value):
        """
        Valida y formatea el número de teléfono internacional
        """
        value = value.strip()
        
        try:
            parsed_number = phonenumbers.parse(value, None)
            
            if not phonenumbers.is_valid_number(parsed_number):
                raise serializers.ValidationError("Número de teléfono no válido.")
            
            # Formatear en formato internacional legible
            formatted_number = phonenumbers.format_number(
                parsed_number, 
                phonenumbers.PhoneNumberFormat.INTERNATIONAL
            )
            
            return formatted_number
            
        except NumberParseException:
            raise serializers.ValidationError(
                "Formato de teléfono inválido. Use formato internacional: +58 4121234567"
            )
    
    def to_representation(self, instance):
        # envolver el dict en SafeDict para evitar KeyError cuando un campo
        # falta en el documento almacenado
        if isinstance(instance, dict):
            instance = SafeDict(instance)

        rep = super().to_representation(instance)
        
        # ***** MODIFICACIÓN CLAVE AQUÍ PARA OCULTAR 'rating' si es None *****
        if rep.get('rating') is None:
            rep.pop('rating', None)
        # *******************************************************************
        
        return rep
    
class ConvertTonegocioSerializer(serializers.Serializer):
    name_business = serializers.CharField(required=True, min_length=4)
    city = serializers.CharField(required=True)
    descripcion = serializers.CharField(required=True)
    phone = serializers.CharField(required=True)
    address = serializers.CharField(required=True)
    horario = HorarioSerializer(many=True, required=True)
    openingTime = TimeFieldToString(required=True)
    closingTime = TimeFieldToString(required=True)

    def create(self, validated_data):
        user = self.context['user']

        negocio_data = user.negocio if isinstance(user.negocio, list) else []
        negocio_data.append(validated_data)

        user.negocio = negocio_data
        user.save()
        return user
    

# utility used by multiple serializers to produce a stable URL from whatever
# value is stored in the model (public_id, full URL, etc).  The previous
# implementation lived as a method on negocioSerializer, which meant other
# serializers (e.g. ClienteSerializer or any third-party serializer such as
# Djoser) still relied on ``.url`` and thus used the global ``cloudinary.config``
# (which might be left pointing at the banner account after some operation).
# By exposing it at module level we can call it consistently everywhere.

def build_cloudinary_url(public_id: str, banner: bool = False) -> str:
    """Return a full HTTPS URL for *public_id* using the configured clouds.

    If *public_id* already looks like a URL it is returned unchanged.  The
    ``banner`` flag chooses between the two named accounts defined in
    ``settings``.  The helper intentionally does **not** add a version; when a
    URL string is stored we preserve whatever version Cloudinary gave us.  If
    only a bare public_id is available the generated URL will omit the version
    and Cloudinary will serve the latest version automatically.
    """
    from django.conf import settings
    import cloudinary.utils

    if not public_id or not isinstance(public_id, str):
        return public_id
    if public_id.startswith(('http://', 'https://')):
        return public_id
    cloud_name = (
        settings.CLOUDINARY_BANNER['CLOUD_NAME'] if banner
        else settings.CLOUDINARY_STORAGE['CLOUD_NAME']
    )
    return cloudinary.utils.cloudinary_url(
        public_id,
        cloud_name=cloud_name,
        secure=True
    )[0]


class negocioSerializer(serializers.ModelSerializer):
    ciudad_coordenadas = serializers.SerializerMethodField()
    negocio = negocioProfileSerializer(many=True, required=True)
    id = serializers.SerializerMethodField()
    email = serializers.EmailField(required=True) 
    profile_imagen = serializers.ImageField(required=False, allow_null=True)
    banner_imagen = serializers.ImageField(required=False, allow_null=True)
    ubicacion_coordenadas = CoordenadasField(  # ← Campo validado
        required=False, 
        allow_null=True,
        help_text='Coordenadas en formato: {"type": "Point", "coordinates": [lat, lng]}'
    )
    distancia_km = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'profile_imagen', 'banner_imagen', 'distancia_km', 'ubicacion_coordenadas', 'biometric',  'negocio', 'ciudad_coordenadas']
        extra_kwargs = {
            'password': {'write_only': True},
            'biometric': {'write_only': True},
            'email': {'read_only': False}  # Permitimos escritura inicial
        }

    def _make_cloud_url(self, public_id: str, banner: bool = False) -> str:
        # keep a thin wrapper for backwards compatibility; delegate to the
        # module-level helper so that all serializers use the same logic.
        return build_cloudinary_url(public_id, banner=banner)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # use helper above rather than trusting storage.url which depends on the
        # global config (which may flip between profile/banner during a
        # request).
        try:
            if instance.profile_imagen:
                rep['profile_imagen'] = self._make_cloud_url(
                    instance.profile_imagen.name,
                    banner=False
                )
        except Exception:
            pass
        try:
            if instance.banner_imagen:
                url = self._make_cloud_url(
                    instance.banner_imagen.name,
                    banner=True
                )
                # strip any extension if earlier code relied on doing so
                if '.' in url.rsplit('/', 1)[-1]:
                    url = url.rsplit('.', 1)[0]
                rep['banner_imagen'] = url
        except Exception:
            pass
        return rep

    def update(self, instance, validated_data):
        # manage profile/image/bandera updates including removals
        # if client passes None for an image, destroy the old one
        from django.conf import settings as _settings
        # profile
        profile_val = validated_data.get('profile_imagen', None)
        if profile_val is None and instance.profile_imagen:
            try:
                cloudinary.uploader.destroy(
                    instance.profile_imagen.name,
                    cloud_name=_settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                    api_key=_settings.CLOUDINARY_STORAGE['API_KEY'],
                    api_secret=_settings.CLOUDINARY_STORAGE['API_SECRET']
                )
            except Exception:
                pass
            instance.profile_imagen = None
        # banner
        banner_val = validated_data.get('banner_imagen', None)
        if banner_val is None and instance.banner_imagen:
            try:
                cloudinary.uploader.destroy(
                    _extract_public_id(instance.banner_imagen),
                    cloud_name=_settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                    api_key=_settings.CLOUDINARY_BANNER['API_KEY'],
                    api_secret=_settings.CLOUDINARY_BANNER['API_SECRET']
                )
            except Exception:
                pass
            instance.banner_imagen = None
        return super().update(instance, validated_data)

    def get_distancia_km(self, obj):
        """Calcula y devuelve la distancia desde el usuario autenticado"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user = request.user
            if (hasattr(user, 'ubicacion_coordenadas') and user.ubicacion_coordenadas and
                hasattr(obj, 'ubicacion_coordenadas') and obj.ubicacion_coordenadas):
                
                try:
                    user_coords = user.ubicacion_coordenadas.get('coordinates', [])
                    negocio_coords = obj.ubicacion_coordenadas.get('coordinates', [])
                    
                    if len(user_coords) == 2 and len(negocio_coords) == 2:
                        user_lng, user_lat = user_coords
                        negocio_lng, negocio_lat = negocio_coords
                        
                        # Calcular distancia
                        from math import radians, sin, cos, sqrt, atan2
                        R = 6371
                        lat1_rad, lng1_rad = radians(user_lat), radians(user_lng)
                        lat2_rad, lng2_rad = radians(negocio_lat), radians(negocio_lng)
                        dlng, dlat = lng2_rad - lng1_rad, lat2_rad - lat1_rad
                        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng/2)**2
                        distancia = R * (2 * atan2(sqrt(a), sqrt(1-a)))
                        
                        return round(distancia, 2)
                        
                except (ValueError, TypeError):
                    pass
        
        return None

    def get_id(self, obj):
        return str(obj.pk) if obj.pk else None
    
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        
        request = self.context.get('request', None)
        
        # Pasa el user_id al contexto del negocioProfileSerializer para el cálculo del rating
        if 'negocio' in rep and rep['negocio']:
            # Pasa el ID del usuario actual para que negocioProfileSerializer pueda calcular el rating
            # 'instance' es la instancia de User, por lo tanto instance.id es el _id del usuario/negocio
            profile_serializer = self.fields['negocio']
            # Asegurarse de que el contexto se propague correctamente a los serializadores anidados
            profile_serializer.context['user_id_for_rating'] = str(instance.id)
            
            # Construir un diccionario seguro con valores por defecto para evitar
            # fallos cuando la entrada es incompleta.
            raw = {}
            if instance.negocio and len(instance.negocio) > 0:
                # copiamos para no mutar el original
                raw = dict(instance.negocio[0])
            # asegurar todas las claves esperadas existen (getattr de SafeDict las
            # devolverá None si faltan)
            for field in ['name_business','city','descripcion','phone','address','horario','openingTime','closingTime']:
                raw.setdefault(field, None)
            safe = SafeDict(raw)

            rep['negocio'] = negocioProfileSerializer(
                safe,
                context={'user_id_for_rating': str(instance.id)}
            ).data

        return {key: value for key, value in rep.items() if value is not None}

    def get_ciudad_coordenadas(self, obj):
        # Preferir valor persistido si existe
        if getattr(obj, 'ciudad_coordenadas', None):
            return obj.ciudad_coordenadas

        point = getattr(obj, 'ubicacion_coordenadas', None)
        if not point:
            return None

        coords = None
        if isinstance(point, dict):
            coords = point.get('coordinates', [])
        elif hasattr(point, 'coords'):
            coords = [point.x, point.y]

        if not coords or len(coords) != 2:
            return None

        parsed = _coords_to_lat_lon(coords)
        if not parsed:
            return None
        lat, lon = parsed
        lat = round(float(lat), 5)
        lon = round(float(lon), 5)
        ciudad = reverse_geocode_ciudad_coordenadas(lat, lon)
        if ciudad:
            try:
                obj.ciudad_coordenadas = ciudad
                obj.save(update_fields=['ciudad_coordenadas'])
            except Exception:
                pass
        return ciudad
    
    # **** AÑADE ESTE MÉTODO PARA LA VALIDACIÓN ****
    def validate_negocio(self, value):
        """
        Valida que el campo 'negocio' no sea una lista vacía.
        También acepta un diccionario único para compatibilidad con documentos
        antiguos que guardaban el campo como objeto en lugar de lista. Si
        recibe un dict lo convierte internamente a lista.
        """
        # convertir dict único a lista para evitar errores posteriores
        if isinstance(value, dict):
            value = [value]

        if not value:  # Si la lista está vacía (o None, aunque required=True ya lo maneja)
            raise serializers.ValidationError(
                "El campo 'negocio' no puede estar vacío. Debe contener al menos un objeto de negocio."
            )

        # ***** AÑADE ESTA NUEVA VALIDACIÓN *****
        if len(value) > 1:
            raise serializers.ValidationError("No puedes tener mas de una negocio")
        
        negocio_data = value[0]
        name_business = negocio_data.get('name_business')
        
        if name_business:
            # Obtener la instancia actual si estamos en una actualización
            instance = getattr(self, 'instance', None)

            # Comparación manual para evitar problemas con consultas sobre JSONField
            target = (name_business or '').strip().lower()
            for u in User.objects.all():
                if not u or not getattr(u, 'negocio', None):
                    continue
                try:
                    nb = u.negocio[0].get('name_business')
                except Exception:
                    nb = None
                if nb and nb.strip().lower() == target:
                    # si es la misma instancia permitimos, sino error
                    if instance and str(u.id) == str(instance.id):
                        break
                    raise serializers.ValidationError({
                        "name_business": "Ya existe un negocio con este nombre."
                    })
        
        return value
    
    def create(self, validated_data):
        # Verificar si el usuario ya existe (por email)
        email = validated_data.get('email')
        existing_user = None
    
        # Guardar referencia a la imagen para limpieza en caso de error
        profile_imagen = validated_data.get('profile_imagen')
        
        if profile_imagen:
            print(f"Profile imagen name: {getattr(profile_imagen, 'name', 'No name')}")
    
        if email:
            try:
                existing_user = User.objects.get(email=email)
            except User.DoesNotExist:
                pass
        
        # Si el usuario existe y se autenticó con Google, actualizarlo
        if existing_user:
            # Verificar autenticación social (forma correcta)
            from social_django.models import UserSocialAuth
            social_auth_exists = UserSocialAuth.objects.filter(user=existing_user, provider='google-oauth2').exists()
            
            if social_auth_exists:
                # Actualizar usuario existente
                instance = existing_user
                
                # Procesar imagen de perfil si se proporciona
                profile_imagen = validated_data.get('profile_imagen')
                if profile_imagen and hasattr(profile_imagen, 'file'):  # Es un archivo, no un public_id
                    # Configurar Cloudinary
                    cloudinary.config(
                        cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                        api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                        api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
                    )
                    
                    # Subir imagen
                    upload_result = cloudinary.uploader.upload(
                        profile_imagen,
                        folder="profile_images/"
                    )
                    # Guardar URL completa para incluir versión y dominio correcto
                    validated_data['profile_imagen'] = (
                        upload_result.get('secure_url') or upload_result.get('url')
                    )
                
                # Procesar datos del negocio
                negocio_data = validated_data.pop('negocio', [])
                if isinstance(negocio_data, dict):
                    negocio_data = [negocio_data]
                
                # NORMALIZAR DATOS DE negocio (igual que para nuevos usuarios)
                for negocio_item in negocio_data:
                    # 🔑 Normalizar horario
                    if "horario" in negocio_item:
                        horario_data = negocio_item["horario"]
            
                        # si viene como dict, convertir a lista
                        if isinstance(horario_data, dict):
                            horario_data = [
                                v for k, v in sorted(horario_data.items(), key=lambda x: int(x[0]))
                            ]
            
                        # Normalizar cada item del horario
                        normalized_horario = []
                        for item in horario_data:
                            if isinstance(item, dict):
                                if "days" in item and isinstance(item["days"], dict):
                                    # convertir days a lista ordenada
                                    item["days"] = [
                                        v for k, v in sorted(item["days"].items(), key=lambda x: int(x[0]))
                                    ]
                                normalized_horario.append(item)
            
                        negocio_item["horario"] = normalized_horario
            
                    # 🔑 Convertir horas (ya son `time` por to_internal_value → reconvertir a str)
                    if "openingTime" in negocio_item and isinstance(negocio_item["openingTime"], time):
                        negocio_item["openingTime"] = negocio_item["openingTime"].strftime("%H:%M")
                    if "closingTime" in negocio_item and isinstance(negocio_item["closingTime"], time):
                        negocio_item["closingTime"] = negocio_item["closingTime"].strftime("%H:%M")
                
                # Actualizar campos del usuario (excluyendo password)
                for attr, value in validated_data.items():
                    if attr != 'password':  # No actualizar password para usuarios existentes
                        setattr(instance, attr, value)
                
                # Asignar datos del negocio
                instance.negocio = negocio_data
                instance.is_active = True  # Activar la cuenta si estaba inactiva
                instance.save()
                
                return instance
        
        # CÓDIGO PARA NUEVOS USUARIOS (sin cambios)
        # Procesar imagen de perfil MANUALMENTE con la cuenta correcta
        if profile_imagen and hasattr(profile_imagen, 'file'):
            # Configurar Cloudinary para cuenta principal
            cloudinary.config(
                cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
            )
            
            # Subir imagen
            upload_result = cloudinary.uploader.upload(
                profile_imagen,
                folder="profile_images/"
            )
            
            # Guardar URL completa
            validated_data['profile_imagen'] = (
                upload_result.get('secure_url') or upload_result.get('url')
            )
            print(f"Imagen de perfil subida a cuenta principal: {validated_data['profile_imagen']}")
        
        
        negocio_data = validated_data.pop('negocio', [])
        
        for negocio_item in negocio_data:
            # 🔑 Normalizar horario
            if "horario" in negocio_item:
                horario_data = negocio_item["horario"]
        
                # si viene como dict, convertir a lista
                if isinstance(horario_data, dict):
                    horario_data = [
                        v for k, v in sorted(horario_data.items(), key=lambda x: int(x[0]))
                    ]
        
                # Normalizar cada item del horario
                normalized_horario = []
                for item in horario_data:
                    if isinstance(item, dict):
                        if "days" in item and isinstance(item["days"], dict):
                            # convertir days a lista ordenada
                            item["days"] = [
                                v for k, v in sorted(item["days"].items(), key=lambda x: int(x[0]))
                            ]
                        normalized_horario.append(item)
        
                negocio_item["horario"] = normalized_horario
        
            # 🔑 Convertir horas (ya son `time` por to_internal_value → reconvertir a str)
            if "openingTime" in negocio_item and isinstance(negocio_item["openingTime"], time):
                negocio_item["openingTime"] = negocio_item["openingTime"].strftime("%H:%M")
            if "closingTime" in negocio_item and isinstance(negocio_item["closingTime"], time):
                negocio_item["closingTime"] = negocio_item["closingTime"].strftime("%H:%M")
        
        
        # Crear usuario
        # Si se está creando un negocio y no se proporcionó `username`,
        # evitar dejar `username=None` porque el validador de MongoDB exige
        # un tipo string; usamos cadena vacía para cumplir la validación.
        if (not validated_data.get('username')) and negocio_data:
            validated_data['username'] = ''

        user = User(**validated_data)
        
        # Solo establecer password si se proporciona (para usuarios sociales puede no venir)
        if 'password' in validated_data and validated_data['password']:
            user.set_password(validated_data["password"])
        
        user.is_active = False  # Al crear, la cuenta no está activa
        user.negocio = negocio_data  # Lista final normalizada
        
        try:
            user.save()
            return user
        except Exception as e:
            # **** LIMPIEZA COMPLETA: Eliminar todas las imágenes si hay error ****
            if 'profile_imagen' in validated_data and validated_data['profile_imagen']:
                try:
                    cloudinary.config(
                        cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                        api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                        api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
                    )
                    cloudinary.uploader.destroy(validated_data['profile_imagen'])
                    print(f"Imagen de perfil eliminada: {validated_data['profile_imagen']}")
                except Exception as delete_error:
                    print(f"Error al eliminar imagen de perfil: {delete_error}")
        
            # Verificar si el error es por name_business duplicado
            error_msg = str(e).lower()
            if "name_business" in error_msg or "duplicate" in error_msg:
                raise serializers.ValidationError({
                    "name_business": "Ya existe un negocio con este nombre."
                })
        
            raise serializers.ValidationError({
                "detail": f"Error al crear el negocio: {str(e)}"
            })

    def update(self, instance, validated_data):
        # Compatibilidad con documentos antiguos donde ``negocio`` era un dict
        # en lugar de una lista. Convertimos en el momento de ejecución para que
        # el resto de la lógica asuma siempre una lista.
        if instance.negocio and isinstance(instance.negocio, dict):
            instance.negocio = [instance.negocio]

        try:
            password = validated_data.pop('password', None)
            if password:
                instance.set_password(password)

            # asegurarnos de no propagar un username nulo en el diccionario
            if 'username' in validated_data and validated_data['username'] is None:
                validated_data['username'] = ''

            # permitir borrado explícito de imágenes
            if 'profile_imagen' in validated_data and validated_data['profile_imagen'] is None and instance.profile_imagen:
                try:
                    cloudinary.uploader.destroy(
                        _extract_public_id(instance.profile_imagen),
                        cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                        api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                        api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
                    )
                except Exception:
                    pass
                instance.profile_imagen = None

            if 'banner_imagen' in validated_data and validated_data['banner_imagen'] is None and instance.banner_imagen:
                try:
                    cloudinary.uploader.destroy(
                        _extract_public_id(instance.banner_imagen),
                        cloud_name=config('CLOUDINARY_BANNER_CLOUD_NAME'),
                        api_key=config('CLOUDINARY_BANNER_API_KEY'),
                        api_secret=config('CLOUDINARY_BANNER_API_SECRET')
                    )
                except Exception:
                    pass
                instance.banner_imagen = None

            # Procesar imagen de perfil MANUALMENTE si hay cambios
            profile_imagen = validated_data.get('profile_imagen')
            old_profile_imagen = instance.profile_imagen
            
            if profile_imagen and profile_imagen != old_profile_imagen:
                # Configurar Cloudinary para cuenta principal
                cloudinary.config(
                    cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
                    api_key=config('CLOUDINARY_PROFILE_API_KEY'),
                    api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
                )
                
                # Subir nueva imagen
                upload_result = cloudinary.uploader.upload(
                    profile_imagen,
                    folder="profile_images/"
                )
                
                # Eliminar imagen anterior si existe
                if old_profile_imagen:
                    try:
                        cloudinary.uploader.destroy(_extract_public_id(old_profile_imagen))
                        print(f"Imagen anterior eliminada: {old_profile_imagen}")
                    except Exception as delete_error:
                        print(f"Error al eliminar imagen anterior: {delete_error}")
                
                # Guardar URL completa en lugar de solo public_id
                validated_data['profile_imagen'] = upload_result.get('secure_url') or upload_result.get('url')
                print(f"Nueva imagen de perfil subida: {validated_data['profile_imagen']}")

            # Procesar banner si hay un archivo nuevo
            banner_imagen = validated_data.get('banner_imagen')
            old_banner = instance.banner_imagen
            if banner_imagen and banner_imagen != old_banner:
                # configurar credenciales de la cuenta de banner
                cloudinary.config(
                    cloud_name=config('CLOUDINARY_BANNER_CLOUD_NAME'),
                    api_key=config('CLOUDINARY_BANNER_API_KEY'),
                    api_secret=config('CLOUDINARY_BANNER_API_SECRET')
                )
                upload_result = cloudinary.uploader.upload(
                    banner_imagen,
                    folder="banner_images/"
                )
                # destruir el viejo a partir de su public_id
                if old_banner:
                    try:
                        cloudinary.uploader.destroy(_extract_public_id(old_banner))
                        print(f"Banner anterior eliminado: {old_banner}")
                    except Exception as delete_error:
                        print(f"Error al eliminar banner anterior: {delete_error}")
                # guardar la URL completa (incluye versión correcta y extension)
                validated_data['banner_imagen'] = upload_result.get('secure_url') or upload_result.get('url')
                print(f"Nuevo banner subido: {validated_data['banner_imagen']}")
        
            
            negocio_data_from_request = validated_data.pop('negocio', None)
            if isinstance(negocio_data_from_request, dict):
                negocio_data_from_request = [negocio_data_from_request]
            
            if negocio_data_from_request is not None:
                # Obtener el perfil existente o crear uno nuevo
                existing_negocio = instance.negocio[0] if instance.negocio else {}
                new_negocio_data = negocio_data_from_request[0] if negocio_data_from_request else {}
                
                # *** MANEJO CORRECTO DE ACTUALIZACIÓN PARCIAL ***
                # Fusionar los campos nuevos sobre los existentes; el dict
                # resultante contendrá todos los valores que vienen en la
                # solicitud, preservando únicamente aquellos campos que no se
                # permiten modificar (rating, comments, etc.).
                merged_data = existing_negocio.copy()

                # Aplique todos los valores entrantes
                merged_data.update(new_negocio_data)

                # Convertir cualquier horario anidado/mal formado a la forma
                # esperada (lista de dicts con días en lista) — la misma
                # normalización que en create().
                if 'horario' in new_negocio_data:
                    merged_data['horario'] = new_negocio_data['horario']

                # Convertir tiempos a string si es necesario
                for time_field in ['openingTime', 'closingTime']:
                    if time_field in merged_data and isinstance(merged_data[time_field], time):
                        merged_data[time_field] = merged_data[time_field].strftime('%H:%M')

                # Mantener campos protegidos que el cliente no puede tocar
                protected_fields = ['rating', 'comments']
                for field in protected_fields:
                    if field in existing_negocio:
                        merged_data[field] = existing_negocio[field]

                # *** CONVERTIR OBJETOS time A STRING ANTES DE GUARDAR ***
                self._convert_time_to_string(merged_data)

                # Asignar los datos fusionados
                instance.negocio = [merged_data]
        
            # Actualizar otros campos
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
    
            instance.save()
            return instance
        
        except Exception as e:
            # Mostrar el error real en lugar de uno genérico
            import traceback
            tb = traceback.format_exc()
            error_message = str(e) or repr(e)
            print(f"Error completo: {error_message}\n{tb}")  # Para debugging
            raise serializers.ValidationError({
                "detail": f"Error al actualizar el negocio: {error_message}"
            })
    
    def _convert_time_to_string(self, data):
        """Convierte objetos time a string para MongoDB"""
        time_fields = ['openingTime', 'closingTime']
        
        for field in time_fields:
            if field in data and isinstance(data[field], time):
                data[field] = data[field].strftime('%H:%M')
        
        # También convertir times en horarios si existen
        if 'horario' in data and isinstance(data['horario'], list):
            for horario_item in data['horario']:
                if isinstance(horario_item, dict):
                    for time_field in time_fields:
                        if time_field in horario_item and isinstance(horario_item[time_field], time):
                            horario_item[time_field] = horario_item[time_field].strftime('%H:%M')

    

    def validate(self, data):
        # **** NUEVA VALIDACIÓN: Verificar email único ANTES de procesar imágenes ****
        email = data.get('email')
        if email:
            # Si es creación (no hay instancia) o el email está cambiando
            if not self.instance or email != self.instance.email:
                if User.objects.filter(email=email).exists():
                    raise serializers.ValidationError({
                        "email": "Ya existe un usuario con este email."
                    })
        
        # Validar name_business único (solo para creación)
        if not self.instance and 'negocio' in data:
            negocio_data = data['negocio']
            if negocio_data and len(negocio_data) > 0:
                name_business = negocio_data[0].get('name_business')
                if name_business:
                    target = (name_business or '').strip().lower()
                    for u in User.objects.all():
                        if not u or not getattr(u, 'negocio', None):
                            continue
                        try:
                            nb = u.negocio[0].get('name_business')
                        except Exception:
                            nb = None
                        if nb and nb.strip().lower() == target:
                            raise serializers.ValidationError({
                                "name_business": "Ya existe un negocio con este nombre."
                            })
                
        # Validación para evitar modificación del email en updates
        if self.instance and 'email' in self.initial_data:
            if self.initial_data['email'] != self.instance.email:
                raise serializers.ValidationError({
                    "email": "El email no puede ser modificado. Use el endpoint de auth/email/reset/ para actualizar el email."
                })
        
        
        
        # Campos que están explícitamente definidos en este serializador y son para entrada
        expected_input_fields = {'profile_imagen', 'banner_imagen', 'ubicacion_coordenadas', 'email', 'password', 'biometric', 'negocio'}
        
        # Campos de business que pueden venir en el nivel principal pero serán movidos
        negocio_fields = {'name_business', 'city', 'descripcion', 'phone', 'address', 'horario', 'openingTime', 'closingTime'}
        
        # Solo verificar campos de primer nivel, ignorar campos anidados como negocio[0][services][0][imagen][0]
        top_level_fields = set(self.initial_data.keys())
        
        # Filtrar solo campos de primer nivel (sin corchetes)
        simple_fields = {field for field in top_level_fields if '[' not in field and ']' not in field}
        
        # Excluir campos de negocios que serán procesados por to_internal_value
        simple_fields = simple_fields - negocio_fields
        
        # Encontrar campos que fueron enviados pero no son esperados por este serializer
        extra_fields = simple_fields - expected_input_fields
        
        if extra_fields:
            raise serializers.ValidationError(
                f"Campos no permitidos para negocios: {', '.join(sorted(list(extra_fields)))}. "
                f"Campos válidos para negocios: {', '.join(sorted(list(expected_input_fields)))}"
            )
        
        return data
    


#####################################################3Ubicacion coordenadas

class LocationField(serializers.JSONField):
    def to_internal_value(self, data):
        if isinstance(data, dict) and 'coordinates' in data and 'type' in data:
            if data['type'] == 'Point' and len(data['coordinates']) == 2:
                # Validar que las coordenadas sean números válidos
                lat, lng = data['coordinates']
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return data
        raise serializers.ValidationError("Formato de ubicación inválido. Use: {'type': 'Point', 'coordinates': [lat, lng]}")
    
class negocioCercanaSerializer(negocioSerializer):
    distancia = serializers.SerializerMethodField()
    
    class Meta(negocioSerializer.Meta):
        fields = negocioSerializer.Meta.fields + ['distancia', 'ciudad_coordenadas', 'address']
    
    def get_distancia(self, obj):
        # Obtener la distancia del contexto
        distancias = self.context.get('distancias', {})
        return distancias.get(obj.id, None)

##############Serializador para comentario

class CommentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True) 
    cliente = serializers.SerializerMethodField(read_only=True)  # Para mostrar info del cliente que comentó
    date = serializers.DateTimeField(format='%d/%m/%y', read_only=True)  # Formato de fecha de salida
    negocio_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(negocio__isnull=False), 
        write_only=True,
        required=False, # Lo hacemos no requerido para PATCH/PUT, aunque el método update lo maneja
                       # Esto puede ayudar a Swagger a inferir que no es para actualización.
                       # Sin embargo, el método 'update' es la última palabra.
    )

    # Campo para la SALIDA de datos (información de el negocio)
    negocio = serializers.SerializerMethodField(read_only=True) 


    class Meta:
        model = Comment
        # Para creación, normalmente los obtienes del contexto/URL.
        fields = ['id', 'cliente', 'negocio_id', 'negocio', 'rating', 'description', 'date']
        read_only_fields = ['id', 'negocio', 'cliente', 'date']

    def get_id(self, obj):
        # Retorna el _id de MongoDB como string
        return str(obj.id)

    def get_cliente(self, obj):
        # Retorna la información del usuario que hizo el comentario
        user_data = {
            'username': obj.cliente.username, # Nombre del usuario que comentó
        }

        # convertimos la imagen a URL de Cloudinary (igual que en ClienteSerializer)
        try:
            if obj.cliente.profile_imagen:
                user_data['profile_imagen'] = build_cloudinary_url(
                    obj.cliente.profile_imagen.name,
                    banner=False
                )
        except Exception:
            # si el campo está roto o la URL falla no interrumpimos la serialización
            pass

        # El ID sólo se expone a staff/autenticados
        request = self.context.get('request', None)
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            if request.user.is_staff:
                user_data['id'] = str(obj.cliente.id)
        # de lo contrario no lo añadimos

        return user_data
    
    def get_negocio(self, obj):
        if obj.negocio and obj.negocio.negocio:
            if obj.negocio.negocio and len(obj.negocio.negocio) > 0:
                return {'nombre': obj.negocio.negocio[0].get('name_business')}
        return None 

    def create(self, validated_data):
        negocio_instance = validated_data.pop('negocio_id')
        cliente = self.context['request'].user  # El usuario autenticado es el cliente.

        # Evita que un negocio comente a otro negocio
        if hasattr(cliente, 'negocio') and cliente.negocio:
            raise serializers.ValidationError({"detail": "Los negocios no pueden dejar comentarios."})

        # Comprueba si el usuario autenticado está intentando comentar sobre su propio negocio (cliente/clienta normal)
        if cliente == negocio_instance:
            raise serializers.ValidationError({"detail": "No puedes comentar tu propia negocio."})

        if Comment.objects.filter(negocio=negocio_instance, cliente=cliente).exists():
            raise serializers.ValidationError({"detail": "Ya has dejado un comentario para este negocio."})

        
        comment = Comment.objects.create(
            negocio=negocio_instance,
            cliente=cliente,
            **validated_data
        )
        self.update_business_rating(negocio_instance) 

        return comment

    def update(self, instance, validated_data):
        if 'negocio_id' in validated_data:
            raise serializers.ValidationError({"negocio": "No se puede cambiar el negocio de un comentario existente."})
        if 'cliente' in validated_data:
            raise serializers.ValidationError({"cliente": "No se puede cambiar el cliente de un comentario existente."})

        old_rating = instance.rating
        
        instance.rating = validated_data.get('rating', instance.rating)
        instance.description = validated_data.get('description', instance.description)
        instance.save()

        if old_rating != instance.rating:
            self.update_business_rating(instance.negocio)

        return instance
    
    # Nuevo método para actualizar el rating de el negocio
    def update_business_rating(self, negocio_instance):
        average_rating = Comment.objects.filter(negocio=negocio_instance).aggregate(Avg('rating'))['rating__avg']
        
        if average_rating is None:
            average_rating = 0.0
        else:
            average_rating = round(average_rating, 2)
        

        # Obtener la lista actual de negocio
        negocio_list = negocio_instance.negocio if negocio_instance.negocio else []
        
        if negocio_list:  # Si hay al menos un elemento
            # Crear una copia del primer diccionario para modificarlo
            updated_negocio = dict(negocio_list[0])
            updated_negocio['rating'] = average_rating
            
            # Reemplazar el primer elemento con la versión actualizada
            negocio_list[0] = updated_negocio
        else:
            # Si no hay datos del negocio, crear una nueva entrada
            negocio_list.append({'rating': average_rating})
        
        # Actualizar el campo negocio en la instancia
        negocio_instance.negocio = negocio_list
        negocio_instance.save()

    def validate(self, data):
        
        # Campos que están explícitamente definidos en este serializador y son para entrada
        expected_input_fields = {'negocio_id', 'rating', 'description'}
        
        initial_keys = set(self.initial_data.keys())
        
        # Encontrar campos que fueron enviados pero no son esperados por este serializer
        extra_fields = initial_keys - expected_input_fields
        
        if extra_fields:
            raise serializers.ValidationError(
                f"Campos no permitidos para comentarios: {', '.join(sorted(list(extra_fields)))}. "
                f"Campos válidos para comentarios: {', '.join(sorted(list(expected_input_fields)))}"
            )
        return data
    
class ServicioSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField(read_only=True) 
    negocio = serializers.SerializerMethodField(read_only=True) 
    imagenes = serializers.ListField(
        child=serializers.ImageField(),  # archivos de imagen
        write_only=True,
        required=False,
        allow_empty=True
    )
    mantener_imagen_urls = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="URLs separadas por coma de las imágenes que quieres mantener"
    )
    precio = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        required=False, allow_null=True
    )
    MONEDAS = ["ARS","BOB","BRL","CLP","COP","CRC","CUP""DOP","USD","EUR","GTQ","GYD""HTG","HNL", "MXN", "NIO","PAB","PYG","PEN","SRD","TTD","UYU","VES"]
    moneda = serializers.ChoiceField(
        choices=MONEDAS,
        required=False, allow_null=True
    )
    imagen_urls = serializers.SerializerMethodField(read_only=True)  

    class Meta:
        model = Servicio
        fields = ['id', 'negocio', 'titulo', 'description', 'imagen_urls', 'imagenes', 'mantener_imagen_urls', 'precio', 'moneda']

    def get_id(self, obj):
        # Retorna el _id de MongoDB como string
        return str(obj.id)
    
    def get_negocio(self, obj):
        # Retorna solo el name_business de el negocio asociada
        if obj.negocio and obj.negocio.negocio:
            negocio_list = obj.negocio.negocio
            if len(negocio_list) > 0:
                return negocio_list[0].get('name_business')
        return None


    def get_imagen_urls(self, obj):
        """
        Devuelve una lista de URLs a partir del contenido almacenado en el
        campo ``imagen_urls``.  Antes guardábamos únicamente los *public_id* y
        construíamos la URL aquí; a partir de ahora el campo almacenará la
        dirección completa (secure_url) porque es más cómodo para el cliente.
        
        Si por compatibilidad aún hay algún *public_id* suelto lo convertimos
        con ``CloudinaryImage`` como antes.
        """
        urls = []
        for item in obj.imagen_urls or []:
            if isinstance(item, str) and item.startswith(('http://', 'https://')):
                urls.append(item)
            else:
                try:
                    urls.append(cloudinary.CloudinaryImage(item).build_url(secure=True))
                except Exception:
                    # en caso de que el valor no pueda transformarse, lo dejamos tal cual
                    urls.append(item)
        return urls

    def validate_imagenes(self, value):
        """
        Validación adicional para las imágenes incluyendo contenido inapropiado
        """
        
        if len(value) > 4:
            raise serializers.ValidationError("No se pueden subir más de 4 imágenes")

        valid_mime_types = ['image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']

        for image_file in value:
            # Verificar tipo MIME real
            if hasattr(image_file, 'content_type') and image_file.content_type:
                if image_file.content_type not in valid_mime_types:
                    raise serializers.ValidationError(
                        f"Tipo de archivo no permitido: {image_file.content_type}. "
                        f"Solo se permiten imágenes (JPEG, PNG, GIF, BMP, WEBP)"
                    )

            # Validar tamaño máximo (5MB)
            max_size = 5 * 1024 * 1024
            if hasattr(image_file, 'size') and image_file.size > max_size:
                raise serializers.ValidationError(
                    f"La imagen {image_file.name} es demasiado grande. "
                    f"Tamaño máximo permitido: 5MB"
                )
            
            # 🔥 NUEVA VALIDACIÓN: Contenido inapropiado
            if not image_validator.is_image_safe(image_file):
                raise serializers.ValidationError(
                    f"La imagen '{image_file.name}' contiene contenido inapropiado y no puede ser publicada. "
                    f"Por favor, selecciona una imagen apropiada para tu publicacion del servicio."
                )

        return value
    
    def create(self, validated_data):
        request = self.context.get('request')
    
        if not request or not hasattr(request, 'user') or request.user.is_anonymous:
            raise serializers.ValidationError("Debe estar autenticado para crear un servicio.")
    
        user = request.user
    
        if not user.negocio:
            raise serializers.ValidationError("Solo los negocios pueden crear servicios.")
    
        imagenes = validated_data.pop('imagenes', [])
        imagen_urls = []
    
        try:
            for img in imagenes:
                # Validar nuevamente antes de subir (doble verificación)
                if not image_validator.is_image_safe(img):
                    raise serializers.ValidationError(
                        "Una de las imágenes contiene contenido inapropiado y no puede ser subida."
                    )
                
                upload_result = cloudinary.uploader.upload(
                    img,
                    folder="services_images/",
                    cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                    api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                    api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
                )
                # guardar la URL segura en lugar del public_id
                imagen_urls.append(upload_result.get('secure_url') or upload_result.get('url'))
    
            validated_data['imagen_urls'] = imagen_urls
            validated_data['negocio'] = user
    
            servicio = Servicio.objects.create(**validated_data)
            return servicio
    
        except serializers.ValidationError:
            # Re-lanzar ValidationError específico de contenido inapropiado
            raise
        except Exception as e:
            # Rollback si algo falla
            from .serializers import _extract_public_id as _extract
            for url in imagen_urls:
                try:
                    public_id = _extract(url)
                    cloudinary.uploader.destroy(
                        public_id,
                        cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                        api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                        api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
                    )
                except:
                    pass
            raise e

    def update(self, instance, validated_data):
        from .nsfw_detector import image_validator  # Import aquí

        if 'negocio' in validated_data:
            raise serializers.ValidationError({"negocio": "No se puede cambiar el negocio de un servicio existente."})
        
        imagenes = validated_data.pop('imagenes', None)
        mantener_imagen_urls = validated_data.pop('mantener_imagen_urls', None)

        # Actualizar título y descripción si fueron enviados
        instance.titulo = validated_data.get('titulo', instance.titulo)
        instance.description = validated_data.get('description', instance.description)

        # Actualizar imágenes (parciales / reemplazos)
        old_urls = instance.imagen_urls or []

        # Normalizamos mantener_imagen_urls para admitir:
        # - valor único string (form-data key: mantener_imagen_urls)
        # - coma-separado string (form-data key: mantener_imagen_urls)
        # - lista list (mantener_imagen_urls[] en algunos clientes)
        if isinstance(mantener_imagen_urls, str):
            # Aceptamos comas como separador (Postman envío único texto)
            parsed = [s.strip() for s in mantener_imagen_urls.split(',') if s.strip()]
            mantener_imagen_urls = parsed
        elif mantener_imagen_urls is None:
            mantener_imagen_urls = old_urls[:]
        elif not isinstance(mantener_imagen_urls, list):
            mantener_imagen_urls = [mantener_imagen_urls]

        # Solo conservar URLs existentes y exactas
        keep_urls = [u for u in mantener_imagen_urls if u in old_urls]
        remove_urls = [u for u in old_urls if u not in keep_urls]

        # 1) Eliminar de Cloudinary las imágenes que ya no se mantendrán
        for old_url in remove_urls:
            try:
                public_id = _extract_public_id(old_url)
                cloudinary.uploader.destroy(
                    public_id,
                    cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                    api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                    api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
                )
            except Exception as e:
                print(f"Error eliminando {old_url}: {e}")

        final_urls = keep_urls[:]

        # 2) Subir nuevas imágenes si se envían
        if imagenes:
            for img in imagenes:
                if not image_validator.is_image_safe(img):
                    raise serializers.ValidationError(
                        "Una de las nuevas imágenes contiene contenido inapropiado."
                    )
                upload_result = cloudinary.uploader.upload(
                    img,
                    folder="services_images/",
                    cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                    api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                    api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
                )
                final_urls.append(upload_result.get('secure_url') or upload_result.get('url'))

        # 3) Validar límite de máximo 4 imágenes
        if len(final_urls) > 4:
            raise serializers.ValidationError("No se pueden tener más de 4 imágenes en un servicio.")

        instance.imagen_urls = final_urls

        # actualizar precio/moneda si se enviaron
        moneda = validated_data.get("moneda")
        precio = validated_data.get("precio")
        if moneda is not None:
            instance.moneda = moneda
        if precio is not None:
            instance.precio = precio

        if precio is not None and moneda is None:
            raise serializers.ValidationError(
                {"moneda": "Debe especificar la moneda si indica un precio."}
            )
       
        # Validar campos inesperados del payload
        expected_input_fields = {'titulo', 'description', 'imagenes', 'mantener_imagen_urls', 'precio', 'moneda'}
        top_level_fields = set(self.initial_data.keys())
        simple_fields = {field for field in top_level_fields if '[' not in field and ']' not in field}
        extra_fields = simple_fields - expected_input_fields
        if extra_fields:
            raise serializers.ValidationError(
                f"Campos no permitidos para negocios: {', '.join(sorted(list(extra_fields)))}. "
                f"Campos válidos para negocios: {', '.join(sorted(list(expected_input_fields)))}"
            )

        # finalmente guardar y devolver el objeto
        instance.save()
        return instance


############################33LOGIN
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        User = get_user_model()  # Obtiene el modelo de usuario actual
        try:
            user = User.objects.get(email=email)  # Busca el usuario por email
        except User.DoesNotExist:
            raise serializers.ValidationError(_('Invalid email or password.'))
        if not user.check_password(password):  # Verifica la contraseña
            raise serializers.ValidationError(_('Invalid email or password.'))
        
        attrs['user'] = user
        return attrs
    
######################################TOKEN
class RefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()
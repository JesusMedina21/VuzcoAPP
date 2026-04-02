import requests
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
import logging
import cloudinary
import cloudinary.uploader
logger = logging.getLogger(__name__)
User = get_user_model()
from decouple import config
from social_core.exceptions import AuthException
from django.db import IntegrityError
from social_django.models import UserSocialAuth
from django.urls import reverse
from django.http import HttpResponseRedirect
from urllib.parse import urlencode
import random
import string

def save_profile_picture(backend, user, response, *args, **kwargs):
    """
    Pipeline para guardar la foto de perfil de Google en Cloudinary
    con mejor manejo de errores y verificación
    """
    # Solo procesar para Google OAuth2
    if backend.name != 'google-oauth2':
        return {}
    
    # Verificar que tenemos usuario y respuesta
    if not user or not response:
        #print("❌ Usuario o respuesta no disponibles")
        return {}
    
    # Obtener URL de la imagen de perfil
    profile_picture_url = response.get('picture')
    if not profile_picture_url:
        #print("⚠️  No se encontró URL de imagen de perfil en la respuesta")
        return {}
    
    try:
        
        cloudinary.config(
            cloud_name=config('CLOUDINARY_PROFILE_CLOUD_NAME'),
            api_key=config('CLOUDINARY_PROFILE_API_KEY'),
            api_secret=config('CLOUDINARY_PROFILE_API_SECRET')
        )
        
        #print(f"📥 Descargando imagen de: {profile_picture_url}")
        
        # Descargar la imagen de Google
        image_response = requests.get(profile_picture_url, stream=True, timeout=10)
        image_response.raise_for_status()
        
        #print(f"✅ Imagen descargada correctamente")
        
        # Subir a Cloudinary en la carpeta profile_images
        upload_result = cloudinary.uploader.upload(
            image_response.content,
            folder="profile_images/",
            public_id=f"user_{user.id}",  # Prefijo para evitar conflictos
            resource_type="image",
            overwrite=True,
            transformation=[
                {'width': 200, 'height': 200, 'crop': 'fill'},
                {'quality': 'auto', 'fetch_format': 'auto'}
            ]
        )
        
        # Obtener la URL segura de Cloudinary
        secure_url = upload_result.get('secure_url') or upload_result.get('url')
        #print(f"☁️  Imagen subida a Cloudinary: {secure_url}")
        # Guardar la URL completa en el usuario para evitar problemas de dominio/versión
        user.profile_imagen = secure_url
        user.save()
        
        #print(f"✅ Imagen de perfil guardada para usuario {user.email}")
        
        return {'user': user}

    except requests.RequestException as e:
        print(f"❌ Error al descargar la imagen de Google: {e}")
    except cloudinary.exceptions.Error as e:
        print(f"❌ Error de Cloudinary: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
    
    return {}


class AccountAlreadyExists(AuthException):
    """Excepción personalizada para cuentas ya existentes"""
    def __init__(self, backend, email):
        super().__init__(backend, f"Ya existe una cuenta con el email {email}")

def get_username(strategy, details, backend, response, user=None, *args, **kwargs):
    """
    Genera un username único basado en el email o para Google basado en nombre y apellido + id.
    """
    if backend.name == 'google-oauth2':
        print(f"DEBUG: kwargs en get_username: {kwargs}")
        print(f"DEBUG: details en get_username: {details}")
        print(f"DEBUG: response en get_username: {response}")
        first_name = details.get('first_name', '')
        last_name = details.get('last_name', '')
        google_id = response.get('sub') or response.get('id', '')
        base_username = f"{first_name}{last_name}{google_id}".lower().replace(' ', '')
        username = base_username
        
        print(f"DEBUG: Generando username para Google: first_name={first_name}, last_name={last_name}, google_id={google_id}, base_username={base_username}")
        
        # Si base_username está vacío, usar email como base
        if not base_username:
            email = details.get('email', '')
            base_username = email.split('@')[0] + google_id
            username = base_username
            print(f"DEBUG: base_username vacío, usando email base: {base_username}")
        
        # Verificar unicidad y agregar sufijo aleatorio si es necesario
        while User.objects.filter(username=username).exists():
            suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            username = f"{base_username}{suffix}"
            print(f"DEBUG: Username ya existe, probando: {username}")
        
        print(f"DEBUG: Username final para Google: {username}")
        return {'username': username}

    email = details.get('email')
    if not email:
        return {}
    
    # Usar el email como base para el username
    base_username = email.split('@')[0]
    username = base_username
    
    # Verificar si el username ya existe y agregar sufijo numérico si es necesario
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1
    
    return {'username': username}

def create_user(strategy, details, backend, user=None, *args, **kwargs):
    """
    Crea el usuario con el username generado correctamente
    """
    if user:
        return {'is_new': False}

    if backend.name == 'google-oauth2':
        # Registrar usuario social con username generado.
        username = kwargs.get('username')
        print(f"DEBUG: Creando usuario Google con username: {username}")
        if not username:
            print("ERROR: Username es None o vacío para Google!")
        user = User(
            email=details.get('email'),
            first_name=details.get('first_name', ''),
            last_name=details.get('last_name', ''),
            username=username,
            is_active=True,
        )
        user.set_unusable_password()
        user.save()
        return {
            'is_new': True,
            'user': user
        }

    user_fields = {
        'email': details.get('email'),
        'username': kwargs.get('username'),
        'first_name': details.get('first_name', ''),
        'last_name': details.get('last_name', ''),
        'is_active': True
    }

    # Eliminar campos vacíos
    user_fields = {k: v for k, v in user_fields.items() if v is not None and v != ''}

    try:
        user = User.objects.create_user(**user_fields)
        return {
            'is_new': True,
            'user': user
        }
    except IntegrityError as e:
        if 'username' in str(e):
            # Si hay conflicto de username, regenerar
            username_strategy = get_username(strategy, details, backend)
            user_fields['username'] = username_strategy.get('username')
            user = User.objects.create_user(**user_fields)
            return {
                'is_new': True,
                'user': user
            }
        raise


def ensure_unique_association(backend, details, response, *args, **kwargs):
    """
    Forzar que cada email único cree un usuario nuevo
    """
    email = details.get('email')
    if not email:
        return {}
    
    #print(f"📧 Processing email: {email}")
    
    # Buscar si ya existe un usuario con este email
    try:
        existing_user = User.objects.get(email=email)
        #print(f"✅ Usuario existente: {existing_user.email} (ID: {existing_user.id})")
        
        # Verificar si ya está asociado con este backend
        try:
            social = UserSocialAuth.objects.get(provider=backend.name, user=existing_user)
            #print(f"📎 Usuario ya está asociado con {backend.name}")
            return {
                'user': existing_user,
                'is_new': False
            }
        except UserSocialAuth.DoesNotExist:
            # Usuario existe pero no está asociado con Google - ERROR
            print(f"🚫 ERROR: Ya existe cuenta con {email} pero no está asociada a Google")
            raise AccountAlreadyExists(backend, email)
            
    except User.DoesNotExist:
        print(f"🆕 Nuevo usuario: {email}")
        # Dejar que el pipeline continúe y cree nuevo usuario
        return {}

def custom_associate_user(backend, details, response, *args, **kwargs):
    """
    Reemplazo del associate_user original para prevenir conflictos
    """
    email = details.get('email')
    uid = kwargs.get('uid')
    
    #print(f"🔗 Custom associate: {email} (UID: {uid})")
    
    if not email or not uid:
        return {}
    
    # Buscar asociación existente por UID (no por email)
    try:
        social = UserSocialAuth.objects.get(provider=backend.name, uid=uid)
        #print(f"📎 Asociación existente encontrada: {social.uid} -> User {social.user_id}")
        return {
            'user': social.user,
            'is_new': False
        }
    except UserSocialAuth.DoesNotExist:
        # Verificar si el email ya existe en la base de datos
        try:
            existing_user = User.objects.get(email=email)
            print(f"🚫 ERROR: Email {email} ya existe pero no está asociado a Google")
            raise AccountAlreadyExists(backend, email)
        except User.DoesNotExist:
            #print("🆕 Nueva asociación requerida - llamando a associate_user original")
            # Dejar que social_core maneje la asociación normalmente
            return {}
    
def prevent_user_overwrite(backend, details, response, user=None, *args, **kwargs):
    """
    Prevenir que un usuario existente sea sobrescrito
    """
    if user and user.pk:
        email = details.get('email')
        if email and email != user.email:
            #print(f"🚫 ALERTA: Intento de sobrescribir usuario {user.email} con {email}")
            # Forzar creación de nuevo usuario en lugar de sobrescribir
            return {
                'user': None,
                'is_new': True
            }
    return {}

def handle_duplicate_email(strategy, details, response, user=None, *args, **kwargs):
    """
    Maneja específicamente el error de email duplicado
    """
    email = details.get('email')
    if not email:
        return {}
    
    try:
        # Verificar si ya existe un usuario con este email
        existing_user = User.objects.get(email=email)
        
        # Verificar si ya está asociado con Google
        from social_django.models import UserSocialAuth
        try:
            social = UserSocialAuth.objects.get(provider='google-oauth2', user=existing_user)
            # Si ya está asociado, continuar normalmente
            return {'user': existing_user, 'is_new': False}
        except UserSocialAuth.DoesNotExist:
            # Usuario existe pero no está asociado a Google - REDIRIGIR A ERROR
            print(f"🚫 REDIRIGIENDO: Email {email} ya existe en sistema")
            
            # Construir URL de error
            error_url = reverse('oauth-error') + f'?message=No puede iniciar con Google porque ya se creó una cuenta con el email {email}. Por favor inicia sesión con tu contraseña.'
            
            # Redirigir inmediatamente
            return HttpResponseRedirect(error_url)
            
    except User.DoesNotExist:
        # No existe usuario, continuar normalmente
        return {}    
    
def social_auth_exception_handler(backend, strategy, details, response, exception, *args, **kwargs):
    """
    Maneja excepciones específicas del proceso de autenticación social
    """
    if isinstance(exception, AccountAlreadyExists):
        # Construir URL de error
        error_url = reverse('oauth-error') + f'?message={str(exception)}'
        return HttpResponseRedirect(error_url)
    
    elif isinstance(exception, IntegrityError) and 'duplicate key value violates unique constraint' in str(exception):
        # Capturar errores de integridad de base de datos
        email = details.get('email', '')
        error_url = reverse('oauth-error') + f'?message=No puede iniciar con Google porque ya se creó una cuenta con el email {email}'
        return HttpResponseRedirect(error_url)
    
    # Re-lanzar otras excepciones para que Django las maneje normalmente
    raise exception 

def is_ionic_app(request):
    # Detectar si la solicitud viene de la app de Ionic/Capacitor
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    return 'capacitor' in user_agent or 'ionic' in user_agent


def redirect_with_token(strategy, details, response, user=None, *args, **kwargs):
    if user and user.is_authenticated:
        # 1. Generamos los tokens UNA SOLA VEZ
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # 2. Imprimimos EXACTAMENTE lo que generamos
        print("\n" + "="*60)
        print(" DATOS DE USUARIO GOOGLE ")
        print(f"User ID: {user.id}")
        print(f"Access Token: {access_token}")
        print(f"Refresh Token: {refresh_token}")
        print("="*60)

        request = strategy.request
        source_param = request.GET.get('source', '')
        is_from_mobile_app = source_param == 'mobile_app' or is_ionic_app(request)

        if is_from_mobile_app:
            redirect_uri = 'com.vuzco.com://google/callback'
        else:
            redirect_uri = 'https://vuzco.vercel.app/google/callback'

        # 3. Determinar tipo de usuario según el campo negocio en User
        #    negocio no vacío -> 'negocio', vacío o None -> 'cliente'
        user_type = 'cliente'
        try:
            if hasattr(user, 'negocio') and user.negocio:
                user_type = 'negocio'
        except Exception:
            user_type = 'cliente'

        params = urlencode({
            'access': access_token,
            'refresh': refresh_token,
            'user_id': str(user.id),
            'type': user_type
        })

        return HttpResponseRedirect(f'{redirect_uri}?{params}')

    return {'user': user}
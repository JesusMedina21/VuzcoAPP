from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from .models import *
import logging

logger = logging.getLogger(__name__)

from urllib.parse import urlparse # Importa la librería

from django.conf import settings
import cloudinary


@receiver(pre_save, sender=User)
def update_username_in_comments(sender, instance, **kwargs):
    if not instance.pk:  # Solo para actualizaciones, no para creaciones
        return
        
    try:
        old_user = User.objects.get(pk=instance.pk)
        if old_user.username == instance.username:
            return  # No hay cambio en el username
            
        logger.info(f"Username cambiado de {old_user.username} a {instance.username}. Actualizando comentarios...")
        
        # Buscar todas los negocios que tienen comentarios de este usuario
        negocios = User.objects.filter(negocio__isnull=False)
        
        updated_negocios = 0
        updated_comments = 0
        
        for negocio in negocios:
            if not negocio.negocio:
                continue
                
            for negocio_profile in negocio.negocio:
                if not isinstance(negocio_profile, dict) or 'comments' not in negocio_profile:
                    continue
                    
                for comment in negocio_profile['comments']:
                    if (isinstance(comment, dict) and 
                        'user' in comment and 
                        isinstance(comment['user'], dict) and 
                        'id' in comment['user'] and 
                        str(comment['user']['id']) == str(instance.pk) and 
                        comment['user'].get('username') == old_user.username):
                        
                        comment['user']['username'] = instance.username
                        updated_comments += 1
                        negocio.save()  # Guardar después de cada actualización
                        updated_negocios += 1
                        break  # Pasar al siguiente negocio
        
        logger.info(f"Actualizados {updated_comments} comentarios en {updated_negocios} negocios")
        
    except User.DoesNotExist:
        logger.error(f"Usuario con pk {instance.pk} no encontrado al intentar actualizar comentarios")
    except Exception as e:
        logger.error(f"Error al actualizar username en comentarios: {str(e)}")

def get_cloudinary_config(is_service=False):
    """Configuración adecuada según el tipo de imagen"""
    if is_service:
        return {
            'cloud_name': settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
            'api_key': settings.SERVICIOS_CLOUDINARY['API_KEY'],
            'api_secret': settings.SERVICIOS_CLOUDINARY['API_SECRET']
        }
    else:
        return {
            'cloud_name': settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
            'api_key': settings.CLOUDINARY_STORAGE['API_KEY'],
            'api_secret': settings.CLOUDINARY_STORAGE['API_SECRET']
        }


@receiver(pre_save)
def delete_old_images(sender, instance, **kwargs):
    from .models import User  # evitar import circular
    if not isinstance(instance, User):
        return  # Solo aplica a User y sus proxys
    """
    Elimina imágenes antiguas cuando se actualizan.  Antes solo se borraba la
    imagen de perfil, pero el mismo problema ocurría con el banner: cada vez que
    se guardaba el negocio (incluso sin tocar el campo) Cloudinary volvía a
    generar una nueva copia.  Con este receptor nos aseguramos de que  
    - no se suba nada a Cloudinary si la imagen no cambió, y
    - cuando sí cambia se borre la versión anterior.
    """
    if not instance.pk:  # Nuevo usuario, no hay imágenes antiguas
        return
    
    try:
        old_user = User.objects.get(pk=instance.pk)
        # ------ perfil ----------------------------------------------------------
        if old_user.profile_imagen and old_user.profile_imagen != instance.profile_imagen:
            delete_image_from_cloudinary(old_user.profile_imagen.name, is_service=False)
        # ------ banner ----------------------------------------------------------
        if old_user.banner_imagen and old_user.banner_imagen != instance.banner_imagen:
            # A diferencia de la cuenta de perfil, el banner usa CLOUDINARY_BANNER
            delete_image_from_cloudinary(old_user.banner_imagen.name,
                                         is_service=False,
                                         is_banner=True)
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Error al eliminar imágenes antiguas: {e}")

def delete_image_from_cloudinary(image_url_or_id, is_service=False, is_banner=False):
    """
    Elimina una imagen de Cloudinary considerando la cuenta correcta.

    - ``is_service`` selecciona la cuenta de ``SERVICIOS_CLOUDINARY``.
    - ``is_banner`` usa la configuración de ``CLOUDINARY_BANNER``.
      Esto es necesario porque las imágenes de portada se almacenan en
      una nube distinta a las de perfil.

    Si ambos flags son ``False`` se usa la cuenta principal de perfil
    (``CLOUDINARY_STORAGE``).
    """
    try:
        if not image_url_or_id:
            return

        # Configurar según el tipo de imagen
        if is_banner:
            config = {
                'cloud_name': settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                'api_key': settings.CLOUDINARY_BANNER['API_KEY'],
                'api_secret': settings.CLOUDINARY_BANNER['API_SECRET'],
            }
        else:
            config = get_cloudinary_config(is_service)

        cloudinary.config(**config)

        if isinstance(image_url_or_id, str):
            if image_url_or_id.startswith(('http://', 'https://')):
                # Si es URL, extraer public_id
                path = urlparse(image_url_or_id).path
                public_id = path.split('/')[-1].split('.')[0]

                # Verificar si tiene folder en la URL
                if path.count('/') > 1:
                    folder = path.split('/')[-2]
                    public_id = f"{folder}/{public_id}"
            else:
                # Si es public_id, usar directamente
                public_id = image_url_or_id

            # Eliminar de Cloudinary
            result = cloudinary.uploader.destroy(public_id)
            if result.get('result') == 'ok':
                logger.info(f"Imagen {public_id} eliminada de Cloudinary (servicio: {is_service}, banner: {is_banner})")
            else:
                logger.error(f"Error al eliminar {public_id}: {result.get('result')}")

    except Exception as e:
        logger.error(f"Error al eliminar imagen de Cloudinary: {e}")
        
@receiver(post_delete)
def cleanup_user_images_on_delete(sender, instance, **kwargs):
    """
    Elimina todas las imágenes asociadas a un usuario cuando se borra su cuenta.
    El receptor se aplica a *cualquier* modelo porque las bajadas de
    un proxy como `Negocio` solían evitar que el handler se ejecutara
    (el `sender` era la clase proxy y no `User`).  Al quitar el filtro de
    `sender` y comprobar `isinstance` aquí mismo, cubrimos ambos casos.
    """
    from .models import User  # evitar import circular dentro de la función

    if not isinstance(instance, User):
        return

    # Eliminar imagen de perfil si existe
    if instance.profile_imagen:
        try:
            delete_image_from_cloudinary(instance.profile_imagen.name, is_service=False)
        except Exception as e:
            logger.error(f"Error al eliminar imagen de perfil: {e}")

    # Eliminar imagen de banner si existe
    if instance.banner_imagen:
        try:
            delete_image_from_cloudinary(getattr(instance.banner_imagen, 'name', instance.banner_imagen),
                                         is_service=False,
                                         is_banner=True)
        except Exception as e:
            logger.error(f"Error al eliminar imagen de banner: {e}")


@receiver(post_delete, sender=Servicio)
def delete_service_images(sender, instance, **kwargs):
    """
    Elimina imágenes de Cloudinary cuando se borra un servicio.

    ``imagen_urls`` puede contener URLs completas o public_ids; el helper
    extrae el identificador adecuado (incluido el folder).
    """
    from .serializers import _extract_public_id

    try:
        for entry in instance.imagen_urls or []:
            public_id = _extract_public_id(entry)
            cloudinary.uploader.destroy(
                public_id,
                cloud_name=settings.SERVICIOS_CLOUDINARY['CLOUD_NAME'],
                api_key=settings.SERVICIOS_CLOUDINARY['API_KEY'],
                api_secret=settings.SERVICIOS_CLOUDINARY['API_SECRET']
            )
    except Exception as e:
        print(f"Error eliminando imágenes de servicio {instance.id}: {e}")

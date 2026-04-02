from decouple import config
import requests
import logging
import PIL.Image
import io

logger = logging.getLogger(__name__)

class FreeImageValidator:
    def __init__(self):
        self.api_user = config('SIGHTENGINE_API_USER', default='')
        self.api_secret = config('SIGHTENGINE_API_SECRET', default='')
        self.is_configured = bool(self.api_user and self.api_secret)
        
        if not self.is_configured:
            logger.warning("Sightengine no configurado. Agrega SIGHTENGINE_API_USER y SIGHTENGINE_API_SECRET al .env")
    
    def _basic_image_validation(self, image_file):
        """Validación básica de imágenes"""
        try:
            # Verificar que sea una imagen válida
            img = PIL.Image.open(image_file)
            img.verify()
            
            # Reset file pointer
            image_file.seek(0)
            return True
            
        except Exception as e:
            logger.error(f"Validación básica falló: {str(e)}")
            return False
    
    def is_image_safe(self, image_file):
        """
        Valida si una imagen es apropiada usando Sightengine API
        """
        # Primero validación básica
        if not self._basic_image_validation(image_file):
            return False
        
        # Si Sightengine no está configurado, permitir la imagen con advertencia
        if not self.is_configured:
            logger.warning("Sightengine no configurado - omitiendo validación NSFW")
            return True
        
        try:
            # Reset file pointer
            image_file.seek(0)
            
            # Sightengine API
            response = requests.post(
                'https://api.sightengine.com/1.0/check.json',
                files={'media': image_file},
                data={
                    'models': 'nudity-2.0,gore,offensive,text-content',
                    'api_user': self.api_user,
                    'api_secret': self.api_secret
                },
                timeout=10  # Timeout de 10 segundos
            )
            
            # Verificar respuesta HTTP
            if response.status_code != 200:
                logger.error(f"Sightengine API error: HTTP {response.status_code}")
                return True  # Permitir si hay error de API
            
            result = response.json()
            
            # Reset file pointer again
            image_file.seek(0)
            
            # Verificar resultados
            if result.get('status') == 'success':
                nudity = result.get('nudity', {})
                offensive = result.get('offensive', {})
                gore = result.get('gore', {})
                text = result.get('text', {})
                
                # Umbrales de seguridad (ajustables)
                if (nudity.get('sexual_activity', 0) > 0.7 or 
                    nudity.get('sexual_display', 0) > 0.7 or
                    nudity.get('erotica', 0) > 0.8 or
                    offensive.get('prob', 0) > 0.7 or
                    gore.get('prob', 0) > 0.6 or
                    any(profanity.get('prob', 0) > 0.8 for profanity in text.get('profanity', []))):
                    
                    logger.warning(
                        f"Imagen rechazada por contenido inapropiado - "
                        f"Nudity: {nudity}, Offensive: {offensive.get('prob', 0)}, "
                        f"Gore: {gore.get('prob', 0)}"
                    )
                    return False
                
                logger.info("Imagen aprobada por Sightengine")
                return True
            
            # Si la API no responde con success, permitir la imagen
            logger.warning(f"Sightengine API no respondió con success: {result}")
            return True
            
        except requests.exceptions.Timeout:
            logger.error("Sightengine API timeout - omitiendo validación")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexión con Sightengine: {str(e)}")
            return True
        except Exception as e:
            logger.error(f"Error inesperado con Sightengine: {str(e)}")
            return True

# Instancia global
image_validator = FreeImageValidator()
# mixins.py
from pymongo import MongoClient
import logging

logger = logging.getLogger(__name__)

from cloudinary_storage.storage import MediaCloudinaryStorage
import cloudinary
import cloudinary.uploader
from decouple import config

class AutoCleanMongoMixin:
    """Mezcla que elimina campos nulos o vacíos de documentos Mongo después de save()."""

    MONGO_URI = config('MONGODB_URI')
    DB_NAME = config('MONGODB_NAME')
    COLLECTION_NAME = "api_user"

    CLEAN_FIELDS = ['username', 'first_name', 'last_name', 'biometric', 'negocio', 'pending_email', 'profile_imagen', 'banner_imagen', 'ubicacion_coordenadas', 'ciudad_coordenadas']

    def mongo_clean(self):
        unset_fields = {}

        for field in self.CLEAN_FIELDS:
            value = getattr(self, field, None)
        
            # Manejar FileField / ImageField vacíos
            if hasattr(value, "name") and not value.name:
                unset_fields[field] = ""
                continue
        
            # Manejar nulos, vacíos, listas vacías
            if value is None or value == "" or (isinstance(value, list) and not value):
                unset_fields[field] = ""


        if unset_fields:
            client = None
            try:
                client = MongoClient(self.MONGO_URI)
                db = client[self.DB_NAME]
                collection = db[self.COLLECTION_NAME]

                # self.pk ya es el ObjectId que mapea a _id de MongoDB
                # Asegúrate de que self.pk sea un ObjectId válido para la consulta
                mongo_document_id = self.pk 
                
                # if not isinstance(mongo_document_id, ObjectId):
                #     # Si por alguna razón no es un ObjectId directo (Django lo maneja, pero por si acaso)
                #     try:
                #         mongo_document_id = ObjectId(str(self.pk))
                #     except Exception as e:
                #         logger.error(f"Error al convertir self.pk '{self.pk}' a ObjectId: {e}")
                #         return

                logger.info(f"Buscando documento en MongoDB con _id: {mongo_document_id}")

                # ¡CAMBIO CLAVE AQUÍ! Busca por '_id', no por 'id'
                mongo_document = collection.find_one({"_id": mongo_document_id}) 

                if mongo_document:
                    # Si el documento ya se encontró por su _id, no necesitas obtenerlo de nuevo
                    # El mongo_document_id ya es el _id que necesitas para la actualización
                    
                    logger.info(f"Documento encontrado. El _id de MongoDB es: {mongo_document_id}")
                    logger.info(f"Campos a eliminar ($unset): {unset_fields}")
                    logger.info(f"Colección: {self.COLLECTION_NAME}, Base de Datos: {self.DB_NAME}")

                    result = collection.update_one(
                        {"_id": mongo_document_id}, # Usa el _id real de MongoDB para la actualización
                        {"$unset": unset_fields}
                    )
                    logger.info(f"Resultado de la limpieza en MongoDB: Coincidencias {result.matched_count}, Modificados {result.modified_count}")
                    if result.matched_count == 0:
                        logger.warning(f"Advertencia: No se encontró ningún documento para _id: {mongo_document_id} en la colección {self.COLLECTION_NAME} durante la actualización.")
                    if result.modified_count > 0:
                        logger.info(f"Documento con _id: {mongo_document_id} modificado exitosamente.")
                else:
                    logger.warning(f"Advertencia: No se encontró ningún documento en MongoDB con _id: {mongo_document_id}. Esto podría indicar un problema de sincronización o que el documento no se guardó correctamente.")

            except Exception as e:
                logger.error(f"Error durante la operación de limpieza de MongoDB: {e}")
            finally:
                if client:
                    client.close()
        else:
            logger.info("No hay campos para eliminar.")


class BannerCloudinaryStorage(MediaCloudinaryStorage):
    """Storage para fotos de portada- Cuenta Principal"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Configurar Cloudinary para la cuenta principal
        self.cloud_name = config('CLOUDINARY_BANNER_CLOUD_NAME')
        self.api_key = config('CLOUDINARY_BANNER_API_KEY')
        self.api_secret = config('CLOUDINARY_BANNER_API_SECRET')
        
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
    
    def _save(self, name, content):
        """Sobrescribir el método save para usar la cuenta correcta.

        En las pruebas previas el campo `name` venía con el nombre del archivo
        (incluyendo la extensión) y eso terminaba formando un `public_id`
        como `banner_images/archivo.jpg`.  Cuando se genera la URL Django
        incluye esa extensión, mientras que los `profile_imagen` obtenían
        identificadores aleatorios sin extensión.  Para que el comportamiento
        sea idéntico al de los perfiles, simplemente no usamos `name` como
        `public_id`.

        Cloudinary genera un identificador aleatorio cuando no se lo pasas, y
        se coloca dentro de la carpeta especificada con el parámetro
        `folder`.  De esa manera las URLs quedan como
        `banner_images/abcd1234` sin sufijo ".jpg".
        """
        # Configurar Cloudinary para la cuenta principal
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )

        # folder de destino; Cloudinary antepone automáticamente la barra
        folder = 'banner_images/'

        # subir sin public_id explícito para que Cloudinary genere uno random
        result = cloudinary.uploader.upload(
            content.file,
            folder=folder,
            overwrite=True,
            resource_type="image"
        )

        # like ProfileStorage, return URL so the model field holds a full link
        return result.get('secure_url') or result.get('url')

    def url(self, name):
        """Return URL always using the banner account, ignoring global state."""
        import cloudinary.utils
        if not name:
            return ''
        if name.startswith(('http://', 'https://')):
            return name
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        return cloudinary.utils.cloudinary_url(
            name,
            cloud_name=self.cloud_name,
            secure=True
        )[0]


class ProfileCloudinaryStorage(MediaCloudinaryStorage):
    """Storage para fotos de perfil - Cuenta Principal"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Configurar Cloudinary para la cuenta principal
        self.cloud_name = config('CLOUDINARY_PROFILE_CLOUD_NAME')
        self.api_key = config('CLOUDINARY_PROFILE_API_KEY')
        self.api_secret = config('CLOUDINARY_PROFILE_API_SECRET')
        
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
    
    def _save(self, name, content):
        """Sobrescribir el método save para usar la cuenta correcta"""
        # Configurar Cloudinary para la cuenta principal
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        
        # Subir a Cloudinary
        folder = 'profile_images/'
        if not name.startswith(folder):
            name = f"{folder}{name}"
            
        result = cloudinary.uploader.upload(
            content.file,
            public_id=name,
            overwrite=True,
            resource_type="image"
        )
        # return secure URL so the field stores a usable link including version
        return result.get('secure_url') or result.get('url')

    def url(self, name):
        """Always build a URL using the profile cloud, ignoring global state."""
        import cloudinary.utils
        if not name:
            return ''
        if name.startswith(('http://', 'https://')):
            return name
        # when storage saves, it returns a public_id; combine with folder
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        return cloudinary.utils.cloudinary_url(
            name,
            cloud_name=self.cloud_name,
            secure=True
        )[0]

class ServiciosCloudinaryStorage(MediaCloudinaryStorage):
    """Storage para imágenes de servicios - Cuenta Secundaria"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Configurar Cloudinary para la cuenta secundaria
        self.cloud_name = config('CLOUDINARY_SERVICES_CLOUD_NAME')
        self.api_key = config('CLOUDINARY_SERVICES_API_KEY')
        self.api_secret = config('CLOUDINARY_SERVICES_API_SECRET')
        
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
    
    def _save(self, name, content):
        """Sobrescribir el método save para usar la cuenta correcta"""
        # Configurar Cloudinary para la cuenta secundaria
        cloudinary.config(
            cloud_name=self.cloud_name,
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        
        # Subir a Cloudinary
        folder = 'service_images/'
        if not name.startswith(folder):
            name = f"{folder}{name}"
            
        result = cloudinary.uploader.upload(
            content.file,
            public_id=name,
            overwrite=True,
            resource_type="image"
        )
        
        return result['public_id']
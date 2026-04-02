from django.db import models
from django.contrib.auth.models import AbstractUser
from .mixins import *
from django.db.models.signals import pre_save
from django.dispatch import receiver
import logging # Importa logging

logger = logging.getLogger(__name__) # Inicializa el logger

from django.db import models
from django.conf import settings # Importar settings para AUTH_USER_MODEL
from datetime import datetime, timedelta

from django.core.validators import MinValueValidator, MaxValueValidator # Importa los validadores

# Redefinimos el método para que no guarde nada en la coleccion django_admin_log
def disable_log_entry_save(*args, **kwargs):
    pass

class User(AutoCleanMongoMixin, AbstractUser):
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)
    #aqui tengo que indicar por exigencias de Django, que al nombre ya no ser unico
    #lo que va a identificar el usuario como ID seria el email, por lo tanto tengo que
    #sobreescribir el campo email y e identificar el email en USERNAME_FIELD y colocar el
    #REQUIRED_FIELDS a juro porque sino, el codigo no va a funcionar por exigencias del framework
    email = models.EmailField(unique=True)
    pending_email = models.EmailField(blank=True, null=True)  # Nuevo campo
    profile_imagen = models.ImageField(upload_to='profile_images/', storage=ProfileCloudinaryStorage(),  null=True, blank=True)
    banner_imagen = models.ImageField(upload_to='banner_images/', storage=BannerCloudinaryStorage(),  null=True, blank=True)
    #Biometric es el campo que va a necesitar los usuarios para almacenar la huella
    #y pueda iniciar sesion con la huella, biometric guarda sus credenciales como
    #email y password
    # 🔥 NUEVOS CAMPOS DE GEOLOCALIZACIÓN (para todos los usuarios)
    ubicacion_coordenadas = models.JSONField(null=True, blank=True, default=None)
    biometric = models.CharField(max_length=255, null=True, blank=True)
    # Ciudad resuelta por geocoding inverso (persistida para evitar llamadas repetidas)
    ciudad_coordenadas = models.CharField(max_length=200, null=True, blank=True, default=None)
    negocio = models.JSONField(null=True, blank=True, default=None)

    USERNAME_FIELD = 'email'
    # Al dejar esta lista vacía, Django NO pedirá nada más al crear un usuario 
    REQUIRED_FIELDS = []

    CLEAN_FIELDS = ['username', 'first_name', 'last_name', 'biometric', 'negocio', 'pending_email', 'profile_imagen', 'banner_imagen', 'ubicacion_coordenadas', 'ciudad_coordenadas']
    

    def save(self, *args, **kwargs):
        # ⚠️ Normalizar username para que nunca sea `None`.
        # MongoDB schema exige cadena y no acepta null, así que transformamos
        # None -> cadena vacía antes de guardar.
        if self.username is None:
            self.username = ''

        # normalizar campos de imagen para evitar cadenas vacías
        if not self.profile_imagen:  # Si está vacío
            self.profile_imagen = None  # Django lo guarda como null en vez de ""
        if not self.banner_imagen:
            self.banner_imagen = None
        super().save(*args, **kwargs)
        self.mongo_clean()

    def delete(self, *args, **kwargs):
        """Siempre limpiar las imágenes alojadas en Cloudinary.

        El admin ya tiene duplicados, pero conviene que el propio modelo
        realice la eliminación para cubrir cualquier otro sitio donde se
        borre un usuario/negocio.
        """
        try:
            # Se importa aquí para evitar dependencias de circularidad
            import cloudinary.uploader
            from django.conf import settings

            # perfil
            if self.profile_imagen:
                public_id = str(self.profile_imagen.name)
                cloudinary.uploader.destroy(
                    public_id,
                    cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
                    api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
                    api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
                )
            # banner
            if self.banner_imagen:
                public_id = str(self.banner_imagen.name)
                cloudinary.uploader.destroy(
                    public_id,
                    cloud_name=settings.CLOUDINARY_BANNER['CLOUD_NAME'],
                    api_key=settings.CLOUDINARY_BANNER['API_KEY'],
                    api_secret=settings.CLOUDINARY_BANNER['API_SECRET'],
                )
        except Exception:
            # no queremos que un error en Cloudinary impida el borrado
            logger.exception("Error al limpiar imágenes en delete() del usuario")
        super().delete(*args, **kwargs)



    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['-id'] 
        # Asegúrate de que no haya restricciones de unicidad
        unique_together = ()  

class Comment(models.Model):
    negocio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments_received',
        limit_choices_to={'negocio__isnull': False}
    )
    
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments_made'
    )
    
    rating = models.IntegerField(
        validators=[
            MinValueValidator(1, message='El rating mínimo es 1.'),
            MaxValueValidator(5, message='El rating máximo es 5.')
        ]
    )
    description = models.TextField()
    date = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Comentario'
        verbose_name_plural = 'Comentarios'
        unique_together = ('negocio', 'cliente')
        ordering = ['-date']

    def __str__(self):
        # Primero, intenta obtener el nombre del negocio  del JSONField
        business_name = self.negocio.username
        if self.negocio.negocio:
            try:
                # Accede al primer elemento de la lista y luego a la clave 'name_business'
                business_name = self.negocio.negocio[0].get('name_business', self.negocio.username)
            except (KeyError, IndexError):
                # En caso de que no exista la clave o el índice, usa el nombre de usuario
                pass

        return f"Comentario del cliente {self.cliente.first_name} {self.cliente.last_name}, para el negocio {business_name} - Calificacion: {self.rating}"

class Servicio(AutoCleanMongoMixin, models.Model):
    
    negocio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='negocio_servicio',
        limit_choices_to={'negocio__isnull': False}
    )
    titulo = models.TextField(null=False, blank=False)
    description = models.TextField()
    imagen_urls = models.JSONField(default=list)
    precio = models.DecimalField(max_digits=10, decimal_places=2, null=True,blank=True)# Opciones de moneda
    MONEDAS = [
        ("ARS", "Peso argentino"),            
        ("BOB", "Boliviano"),              
        ("BRL", "Real brasileño"),          
        ("CLP", "Peso chileno"),            
        ("COP", "Peso colombiano"),        
        ("CRC", "Colón costarricense"),       
        ("CUP", "Peso cubano"),          
        ("DOP", "Peso dominicano"),          
        ("USD", "Dólar estadounidense"),         
        ("EUR", "Euro"),                    
        ("GTQ", "Quetzal guatemalteco"),      
        ("GYD", "Dólar guyanés"),        
        ("HTG", "Gourde haitiano"),         
        ("HNL", "Lempira hondureño"),       
        ("MXN", "Peso mexicano"),
        ("NIO", "Córdoba nicaragüense"),             
        ("PAB", "Balboa panameño"),        
        ("PYG", "Guaraní paraguayo"),              
        ("PEN", "Sol peruano"),                    
        ("SRD", "Dólar surinamés"),                 
        ("TTD", "Dólar de Trinidad y Tobago"),         
        ("UYU", "Peso uruguayo"),                 
        ("VES", "Bolívar venezolano"),
    ]
    moneda = models.CharField(
        max_length=3,
        choices=MONEDAS,
        null=True,
        blank=True
    )

    CLEAN_FIELDS = ['precio', 'moneda']
    COLLECTION_NAME = "api_servicio"
    
    class Meta:
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'
        ordering = ['-id'] 

    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.mongo_clean()
    
    def __str__(self):
        # Primero, intenta obtener el nombre de el negocio del JSONField
        business_name = self.negocio.username
        if self.negocio.negocio:
            try:
                # Accede al primer elemento de la lista y luego a la clave 'name_business'
                business_name = self.negocio.negocio[0].get('name_business', self.negocio.username)
            except (KeyError, IndexError):
                # En caso de que no exista la clave o el índice, usa el nombre de usuario
                pass

        return f"Servicio: {self.description}. Del negocio: {business_name}"


class ChatMessage(models.Model):
    emisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_messages',
    )
    receptor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_messages'
    )
    mensaje_texto = models.TextField()
    hora_mensaje = models.DateTimeField(auto_now_add=True)
    visto = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Chat'
        verbose_name_plural = 'Chat'
        ordering = ['hora_mensaje']

    def __str__(self):
        emisor = self.emisor or 'Desconocido'
        receptor = self.receptor or 'Desconocido'
        return f"[{self.hora_mensaje}] {emisor} -> {receptor}: {self.mensaje_texto[:50]}"

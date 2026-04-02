from django.apps import AppConfig
from django.contrib import admin

class ApiConfig(AppConfig):
    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'  
    name = 'api'
    verbose_name = 'Vuzco Modelos'

    def ready(self):
        import api.signals  # Asegúrate de crear este archivo

class SocialDjangoConfig(AppConfig):
    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'
    name = 'social_django'

    def ready(self):
        from social_django.models import Association, Nonce, UserSocialAuth
        try:
            admin.site.unregister(Association)
            admin.site.unregister(Nonce)
            admin.site.unregister(UserSocialAuth)
        except admin.exceptions.NotRegistered:
            # En caso de que ya estén desregistrados o no existan en el admin.
            pass
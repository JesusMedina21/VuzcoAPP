from django.contrib.auth.models import Permission

class PermissionRouter:
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if model_name == 'permission' or (app_label == 'auth' and model_name is None):
            return False  # No migrar el modelo Permission
        return None

    def db_for_read(self, model, **hints):
        if model == Permission:
            return None  # No leer de ninguna base de datos
        return None

    def db_for_write(self, model, **hints):
        if model == Permission:
            return None  # No escribir en ninguna base de datos
        return None
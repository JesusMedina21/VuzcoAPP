from django.http import HttpResponseForbidden
from django.conf import settings
import re

class BlockPostmanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'postman' in user_agent:
            return HttpResponseForbidden("Acceso denegado")
        return self.get_response(request)
    
class CustomHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = [
            '/admin/',    # Rutas que se pueden visualizar
            '/static/',   #Para que cargen estilos en el admin
            '/staticfiles/',
            '/serviceworker.js',  # Ruta worker
            '/manifest.json',     # Ruta del manifest
            '/offline/'           # Si tienes una ruta offline para PWA
            '/api/auth/o/',   
            #'/api/docs/',    #Solo en desarrollo se descomenta  y se usa
            #'/api/schema/',  #Solo en desarrollo se descomenta  y se usa
        ]
        # Compilar patrones regex para las rutas que los necesiten
        self.regex_patterns = [
            re.compile(r'^/api/auth/o/'),
            re.compile(r'^/complete/'),
            re.compile(r'^/api/oauth-error/'),  
        ]

    #def __call__(self, request):
    #    # Verifica si la ruta está exenta
    #    if any(request.path.startswith(path) for path in self.exempt_paths):
    #        return self.get_response(request)
    #        
    #    # Verifica el header personalizado
    #    secret_header = request.headers.get(settings.SECURE_API_HEADER)
    #    if secret_header != settings.SECURE_API_VALUE:
    #        return HttpResponseForbidden("Acceso no autorizado")
    #        
    #    return self.get_response(request)
    
#Eliminar registros en la coleccion admin_log_entry que es relativamente el historial de acciones realizadas del admin
class DisableAdminLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.original_save = None  # Inicializa la variable aquí
    def __call__(self, request):
        response = self.get_response(request)
        return response
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Si es una acción del admin, deshabilitar logging
        if hasattr(view_func, 'admin_site'):
            # Deshabilitar temporalmente el logging
            from django.contrib.admin.models import LogEntry
            self.original_save = LogEntry.save  # Guarda el método original
            def noop_save(self, *args, **kwargs):
                return
            LogEntry.save = noop_save
            request._admin_log_disabled = True
        return None
    def process_response(self, request, response):
        # Restaurar el comportamiento original si fue deshabilitado
        if hasattr(request, '_admin_log_disabled'):
            from django.contrib.admin.models import LogEntry
            LogEntry.save = self.original_save  # Usa el método guardado
        return response
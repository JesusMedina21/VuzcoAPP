from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.exceptions import PermissionDenied
from rest_framework import permissions
"""
Este CODIGO ES SOLAMENTE PARA QUE USUARIOS SI SON ADMINS puedan obtener 
las listas de todos los usuarios, eliminar o editar todos los usuarios
O para que un usuario solamente pueda editar su propia informacion 
"""


class MiUsuarioLogin(BasePermission):

    def has_object_permission(self, request, view, obj):
        # Permite a superusuarios/staff cualquier acción
        if request.user.is_superuser or request.user.is_staff:
            return True
            
        # Permite al dueño de su propia cuenta cualquier acción
        return obj.id == request.user.id


class MiUsuario(BasePermission):
    

    def has_object_permission(self, request, view, obj):
        # Permite a superusuarios/staff cualquier acción
        if request.user.is_superuser or request.user.is_staff:
            return True
            
        # Permite al dueño de su propia cuenta cualquier acción
        return str(obj.cliente.id) == str(request.user.id)
    
class Minegocio(BasePermission):
    def has_object_permission(self, request, view, obj):
        # Permite a superusuarios/staff cualquier acción
        if request.user.is_superuser or request.user.is_staff:
            return True
            
        # Permite al dueño de su propia cuenta cualquier acción
        return str(obj.id) == str(request.user.id)  # 👈 Cambio clave aquí
    
class MiServicio(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_staff:
            return True

        # Solo el dueño del negocio puede editar/eliminar sus servicios
        return str(obj.negocio.id) == str(request.user.id)


class ChatMessageParticipantPermission(BasePermission):
    """Permite a participantes del mensaje ver y modificar su propia conversación."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_staff:
            return True

        if obj is None:
            return False
        if obj.emisor == request.user or obj.receptor == request.user:
            if request.method in SAFE_METHODS:
                return True
            if obj.emisor != request.user:
                return False
            elapsed = timezone.now() - obj.hora_mensaje
            if elapsed > timedelta(minutes=30):
                raise PermissionDenied('El mensaje después de 30 minutos de ser enviado no se puede borrar')
            return True

        return False

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vuzco.settings')
import django
django.setup()

from urllib.parse import parse_qs

from django.core.asgi import get_asgi_application
from channels.middleware import BaseMiddleware
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.db import close_old_connections

import api.routing


class JWTAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)
        self.jwt_auth = None

    async def __call__(self, scope, receive, send):
        if self.jwt_auth is None:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            self.jwt_auth = JWTAuthentication()

        close_old_connections()
        query_params = parse_qs(scope.get('query_string', b'').decode())
        raw_token = None
        token_list = query_params.get('token')
        if token_list:
            raw_token = token_list[0]
        if raw_token and raw_token.startswith('Bearer '):
            raw_token = raw_token.split(' ', 1)[1]

        if raw_token:
            try:
                validated_token = self.jwt_auth.get_validated_token(raw_token)
                scope['user'] = self.jwt_auth.get_user(validated_token)
            except Exception:
                from django.contrib.auth.models import AnonymousUser
                scope['user'] = AnonymousUser()

        return await super().__call__(scope, receive, send)


application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': JWTAuthMiddleware(
        AuthMiddlewareStack(
            URLRouter(api.routing.websocket_urlpatterns)
        )
    ),
})
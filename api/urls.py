from django.urls import path, include
from rest_framework import routers
from api import views
from django.conf import settings
from django.conf.urls.static import static

from django.conf import settings
from .views import *
from djoser.views import UserViewSet


#endpoints   
router = routers.DefaultRouter()
router.register(r'clients', views.ClienteViewSet, basename='clientes')
router.register(r'business', views.NegocioViewSet, basename='negocios')
router.register(r'comments', views.ComentarioViewSet)
router.register(r'servicios', views.ServicioViewSet)
router.register(r'chat/messages', views.ChatMessageViewSet, basename='chatmessages')

urlpatterns = [
    path('', include(router.urls)),

    #endpoints   
    path('business/google/', ConvertGoogleUserTonegocioView.as_view(), name='convert-google-to-business'),
    # Endpoints personalizados de Djoser
    path('auth/activate/', CustomUserViewSet.as_view({'post': 'activation'}), name='user-activation'),
    path('auth/activate/new-email/', ActivarNuevoEmailView.as_view(), name='activation-new-email'),
    path('auth/reset/email/', CustomUserViewSet.as_view({'post': 'reset_username'}), name='email-reset'),
    path('auth/reset/email/confirm/', ConfirmarEmail.as_view(), name='reset-email-confirm'), 
    path('auth/reset/password/', CustomUserViewSet.as_view({'post': 'reset_password'}), name='password-reset'),
    path('auth/reset/password/confirm/', CustomUserViewSet.as_view({'post': 'reset_password_confirm'}), name='password-reset-confirm'),
    path('auth/o/login/google-oauth2-documentacion/', views.GoogleOAuth2LoginDocsView.as_view(), name='google-oauth2-doc'),
    path('oauth-error/', OAuthErrorView.as_view(), name='oauth-error'),
    path('auth/o/', include('social_django.urls', namespace='social')),  # << importante
    #La ruta de auth/o es api/auth/o/login/google-oauth2/
    #path('chat/websocket-info/', views.ChatWebsocketInfoView.as_view(), name='chat-websocket-info'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
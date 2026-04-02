"""
URL configuration for vuzco project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from api.views import *

#DRF JWT
#from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

#DRF SPECTACULAR 

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from drf_spectacular.utils import extend_schema_view, extend_schema

#REDIRECCIONAMINENTO

from django.views.generic.base import RedirectView

@extend_schema_view(
    get=extend_schema(exclude=True)  # <- esto la excluye de Swagger
)
class HiddenSchemaView(SpectacularAPIView):
    pass

urlpatterns = [
    path('', include('pwa.urls')), #Siempre de primera o sino no funciona
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')), #ESTO LLAMO LOS ENDPOINTS
    #swagger
    path('api/docs/', SpectacularSwaggerView.as_view(), name='docs'),
    #DRF SPECTACULAR SIN EL SCHEMA NO FUNCIONA DOCS
    path('api/schema/', HiddenSchemaView.as_view(),name='schema'),
    #DRF JWT
    path('api/login/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    #path('djoser/', include('djoser.urls')),
    #path('djoser/', include('djoser.urls.jwt')),

    #REDIRECCIONAMIENTO
    re_path(r'^(?!api/docs/|api/auth/o/login/google-oauth2/).*$', RedirectView.as_view(url='/admin/', permanent=False)),


]

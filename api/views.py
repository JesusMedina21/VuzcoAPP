from django.http import Http404
from rest_framework import viewsets, status, generics
from api.serializers import *
from api.serializers import _is_business_user

from django.shortcuts import render
from django.views import View
# from django.contrib.auth.models import User # Modelo original
from api.models import *
# JWT
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser

#DRF SPECTACULAR
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample, OpenApiParameter

from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from api.permissions import *
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as BaseTokenRefreshView
from django.db.models import Q  #Esta importacion sirve para realizar consultas complejas a la base de datos
from djoser import signals
from djoser.conf import settings as djoser_settings
from djoser.views import UserViewSet

from math import radians, sin, cos, sqrt, atan2

from django.contrib.auth.tokens import default_token_generator
from rest_framework.views import APIView

from api.custom_email import *
from django.db.utils import IntegrityError  # 👈 Importa esta excepción
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.db import transaction
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
import re
from collections import defaultdict

from .pagination import * 
from drf_spectacular.types import OpenApiTypes

VERCEL_API_KEY_SECRET = "ae24638ce08a743c58aea8a35931e76464d8d0a15fed29fc696cfe2bf9806f2f"

#################################################AUTH

@extend_schema(
    request=ConfirmarEmailSerializer,
    description='Confirma el cambio de email usando el UID y token del enlace'
)

class ConfirmarEmail(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ConfirmarEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.user
        token = serializer.validated_data['token']
        new_email = serializer.validated_data["new_email"]

        if not default_token_generator.check_token(user, token):
            return Response(
                {"token": "Token inválido o expirado"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if User.objects.filter(email=new_email).exists():
            return Response(
                {"new_email": ["Este correo electrónico ya está en uso."]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Guardamos directamente en los nuevos campos
        user.pending_email = new_email
        user.email_change_token = default_token_generator.make_token(user)
        user.save()

        email_context = {
            'user': user,
            'new_email': new_email,
            'old_email': user.email,
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': user.email_change_token
        }

        activation_email = CustomEmailReset(request, email_context)
        activation_email.send(to=[new_email])

        return Response(
            {"detail": "Se ha enviado un correo de confirmación al nuevo email"},
            status=status.HTTP_200_OK
        )


@extend_schema(
    request=ActivarEmailSerializer,
    description='Confirma el nuevo email usando el UID y token del enlace'
)
class CustomUserViewSet(UserViewSet):
    def activation(self, request, *args, **kwargs):
        # Validar datos de activación y obtener usuario
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user

        # Marcar cuenta como activa
        user.is_active = True
        user.save()

        # Enviar correo personalizado de confirmación (opcional)
        CustomActivationConfirmEmail(context={'user': user}).send(to=user.email)

        # Generar tokens JWT exactamente igual que en el login
        refresh = RefreshToken.for_user(user)
        tipo_usuario = "negocio" if user.negocio else "cliente"

        return Response({
            'refresh': str(refresh),
            'token': str(refresh.access_token),
            'id': str(user.id),
            'tipo_usuario': tipo_usuario,
            'detail': "¡Cuenta activada con éxito! Bienvenido a Vuzco."
        }, status=status.HTTP_200_OK)

    @extend_schema(
        description="Solicita el cambio de email. Si el correo existe se envía un enlace y se devuelve un mensaje de confirmación.",
        responses={200: OpenApiTypes.OBJECT},
        request=OpenApiTypes.OBJECT,
        examples=[
            OpenApiExample(
                'Ejemplo de solicitud',
                value={"email": "string"}
            )
        ]
    )
    def reset_username(self, request, *args, **kwargs):
        """Personalizamos la respuesta del reset de email username field.

        Djoser devolvía 204 con contenido vacío; nosotros queremos un mensaje
        amigable para el cliente.
        """
        resp = super().reset_username(request, *args, **kwargs)
        if resp.status_code == status.HTTP_204_NO_CONTENT:
            return Response(
                {"detail": "Se ha enviado un enlace a tu email, abre el enlace para poder seguir con el cambio."},
                status=status.HTTP_200_OK,
            )
        return resp

    @extend_schema(
        description="Solicita el cambio de contraseña; envía un correo con enlace y responde con mensaje de confirmación.",
        responses={200: OpenApiTypes.OBJECT},
        request=OpenApiTypes.OBJECT,
        examples=[
            OpenApiExample(
                'Ejemplo de solicitud',
                value={"email": "string"}
            )
        ]
    )
    def reset_password(self, request, *args, **kwargs):
        resp = super().reset_password(request, *args, **kwargs)
        if resp.status_code == status.HTTP_204_NO_CONTENT:
            return Response(
                {"detail": "Se envió un mensaje a su correo para poder cambiar la contraseña, abra el enlace para poder seguir con el cambio."},
                status=status.HTTP_200_OK,
            )
        return resp

    @extend_schema(
        description="Confirma el cambio de contraseña. Devuelve texto de éxito.",
        responses={200: OpenApiTypes.OBJECT},
        request=OpenApiTypes.OBJECT,
        examples=[
            OpenApiExample(
                'Ejemplo de solicitud',
                value={"uid": "string", "token": "string", "new_password": "string"}
            )
        ]
    )
    def reset_password_confirm(self, request, *args, **kwargs):
        resp = super().reset_password_confirm(request, *args, **kwargs)
        if resp.status_code == status.HTTP_204_NO_CONTENT:
            return Response(
                {"detail": "Su contraseña se ha cambiado exitosamente."},
                status=status.HTTP_200_OK,
            )
        return resp
@extend_schema(
    request=ActivarNuevoEmailSerializer,
    description='Confirma el nuevo email usando el UID y token del enlace'
)
class ActivarNuevoEmailView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ActivarNuevoEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.user

        if not user.pending_email:
            return Response(
                {"detail": "No hay cambio de email pendiente"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, serializer.validated_data['token']):
            return Response(
                {"token": "Token inválido o expirado"},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_email = user.pending_email
        old_email = user.email
        
        try:
            with transaction.atomic():
                user.email = new_email
                user.pending_email = None
                user.email_change_token = None
                user.save()
        except IntegrityError:
            return Response(
                {"detail": "Este correo electrónico ya está en uso"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Enviar notificaciones
        email_context = {
            'user': user,
            'new_email': new_email,
            'email': new_email,  # Añade esto para el template
            'old_email': old_email
        }

        confirmation_email = CustomActivationNewEmail(request, email_context)
        confirmation_email.send(to=[new_email])

        notification_email = CustomOldEmailNotification(request, email_context)
        notification_email.send(to=[old_email])

        return Response(
            {"detail": "Email cambiado exitosamente"},
            status=status.HTTP_200_OK
        )


class OAuthErrorView(View):
    template_name = 'oauth_error.html'
    
    def get(self, request, *args, **kwargs):
        error_message = request.GET.get('message', 'No puede iniciar con Google porque ya se creó una cuenta')
        return render(request, self.template_name, {'error_message': error_message})


class GoogleOAuth2LoginDocsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        summary="No probar en SWAGGER, es solo para documentacion",
        description="El endpoint REAL es: /api/auth/o/login/google-oauth2/?redirect_uri=enlace",
        parameters=[
            OpenApiParameter(
                name='redirect_uri',
                type=OpenApiTypes.URI,
                location=OpenApiParameter.QUERY,
                required=True,
                description='URL de retorno después de autenticación de Google'
            )
        ],
        responses={200: OpenApiTypes.OBJECT}
    )
    def get(self, request):
        return Response(
            {
                'detail': 'Uso: /api/auth/o/login/google-oauth2/?redirect_uri=https://vuzco.vercel.app/'
            },
            status=status.HTTP_200_OK
        )

###################################3333333#Cliente###############################################

@extend_schema_view(
    list=extend_schema(tags=['Clientes'],
        summary="Obtener datos de todos los clientes",),
    retrieve=extend_schema(tags=['Clientes'],
       summary="Obtener datos de mi cuenta",),
    create=extend_schema(
        tags=['Clientes'],
        summary="Crear cuenta de cliente",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'first_name': {'type': 'string'},
                    'last_name': {'type': 'string'},
                    'username': {'type': 'string'},
                    'email': {'type': 'string', 'format': 'email'},
                    'password': {'type': 'string', 'format': 'password'},
                    'profile_imagen': {'type': 'string', 'format': 'binary'},
                    'biometric': {'type': 'string'},
                    'ubicacion_coordenadas': {  # ✅ ESTA ES LA CORRECCIÓN
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'example': 'Point'},
                            'coordinates': {
                                'type': 'array',
                                'items': {'type': 'number'},
                                'example': [-16.4897, -68.1193]
                            }
                        },
                        'required': ['type', 'coordinates']
                    }
                },
                'required': ['first_name', 'last_name', 'username', 'email', 'password']
            }
        },
        responses={201: ClienteSerializer}
    ),
    methods=['POST'], tags=['Clientes'], 
    update=extend_schema(exclude=True),  # Oculta el método PUT (update)
    partial_update=extend_schema(
        tags=['Clientes'],
        summary="Editar mi cuenta",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'first_name': {'type': 'string'},
                    'last_name': {'type': 'string'},
                    'username': {'type': 'string'},
                    'password': {'type': 'string'},
                    'biometric': {'type': 'string'},
                    'profile_imagen': {'type': 'string'},
                    'ubicacion_coordenadas': { 
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'example': 'Point'},
                            'coordinates': {
                                'type': 'array',
                                'items': {'type': 'number'},
                                'example': [-16.4897, -68.1193]
                            }
                        }
                    }
                },
                'required': []
            }
        }
    ),    
    destroy=extend_schema(tags=['Clientes'],
        summary="Eliminar mi cuenta",),
)

class ClienteViewSet(viewsets.ModelViewSet):
    queryset = User.objects.filter(negocio__isnull=True)
    serializer_class = ClienteSerializer
    pagination_class = ClientenegocioPagination 

    # 1. Indica que el campo de búsqueda es 'id' (el PK de tu modelo User)
    lookup_field = 'id' 
    # 2. Especifica la expresión regular para un ObjectId de 24 caracteres hexadecimales
    lookup_value_regex = '[0-9a-fA-F]{24}' 

    def get_queryset(self):
        user = self.request.user
        action = getattr(self, 'action', None)

        if action == 'list':
            return User.objects.filter((Q(negocio__isnull=True) | Q(negocio=[])) & Q(is_active=True) & Q(is_staff=False)  )
    
        return super().get_queryset()


    def get_permissions(self):
        action = getattr(self, 'action', None)

        if action == 'create': # Esta linea significa que el endpoint register lo pueda usar cualquiera
            return [AllowAny()]  # Permitir registro sin autenticación
        elif action == 'list':
            # Permitir que CUALQUIER usuario AUTENTICADO acceda a la lista
            return [IsAuthenticated()]
        elif action in ['retrieve', 'partial_update', 'destroy']:
            # Permitir acceso a retrieve, update y destroy solo si el usuario está autenticado

            # Y que el resto de metodos usen IsAuthenticated que significa JWT y el IsSelf que significa
            # que el mismo usuario pueda acceder a su propio recurso, ejemplo el usuario 1 solo acceda al endpoint 1 
            return [IsAuthenticated(), MiUsuarioLogin()]  # 👈 Requiere autenticación y que sea el mismo usuario 
        #El IsAuthenticated es creado automaticamente por Django, MiUsuario es creado manualmente
        return [IsAuthenticated()]
    
    @extend_schema(tags=['Cliente'])
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Usa el serializador para crear el usuario
        user = serializer.save()  # Esto llamará al método create del serializador
        
        # ***** NUEVA LÓGICA PARA ENVIAR EL CORREO DE ACTIVACIÓN *****
        signals.user_registered.send(
            sender=self.__class__, user=user, request=self.request
        )
        if djoser_settings.SEND_ACTIVATION_EMAIL:
            context = {"user": user}
            djoser_settings.EMAIL.activation(self.request, context).send([user.email])
        # ************************************************************
        
        return Response(ClienteSerializer(user).data, status=status.HTTP_201_CREATED)
   
    def update(self, request, *args, **kwargs):
        if not kwargs.get('partial', False):
            return Response(
                {"detail": "Método PUT no permitido. Use PATCH en su lugar."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs) 


###################################3333333#negocios###############################################

###Con este codigo puedo crear negocios con body multiplataform en Postman
def dict_to_list(data):
    """
    Convierte dicts con claves '0','1','2' en listas reales.
    """
    if isinstance(data, dict):
        # convierte todas las claves a str para comparar
        keys = list(data.keys())
        if all(str(k).isdigit() for k in keys):
            return [dict_to_list(data[k]) for k in sorted(keys, key=lambda x: int(x))]
        else:
            return {k: dict_to_list(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [dict_to_list(v) for v in data]
    else:
        return data

    
def nested_dict():
    return defaultdict(nested_dict)

def querydict_to_nested(data):
    result = nested_dict()

    for key, value in data.items():
        parts = re.split(r'\[|\]', key)
        parts = [p for p in parts if p != '']  # limpia vacíos
        d = result
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = value

    return dict(result)

@extend_schema(tags=['Negocios'], summary="Agregar campos de negocio a cuenta registrada con Google")
class ConvertGoogleUserTonegocioView(APIView):
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        request=ConvertTonegocioSerializer,
        responses={200: negocioSerializer},
        description='Convertir usuario de Google en negocio'
    )
    def post(self, request):
        user = request.user
        
        # Verificar que el usuario se autenticó con Google
        social_auth = user.social_auth.filter(provider='google-oauth2').first()
        if not social_auth:
            return Response(
                {"detail": "Este usuario no se autenticó con Google"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar que no sea ya un negocio
        if user.negocio:
            return Response(
                {"detail": "Esta cuenta ya es de un negocio"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Usar el serializador específico para conversión
        serializer = ConvertTonegocioSerializer(
            data=request.data,
            context={'user': user, 'request': request}
        )
        
        if serializer.is_valid():
            user = serializer.save()
            
            # Devolver los datos con el serializador del negocio completo
            negocio_serializer = negocioSerializer(user, context={'request': request})
            return Response(negocio_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
@extend_schema_view(
    list=extend_schema(tags=['Negocios'],
        summary="Obtener datos de todas las negocios",),
    retrieve=extend_schema(tags=['Negocios'], 
       summary="Obtener datos de mi negocio",),
    create=extend_schema(
        tags=['Negocios'],
       summary="Crear cuenta de negocio",
       request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'email': {'type': 'string', 'format': 'email'},
                    'password': {'type': 'string'},
                    'profile_imagen': {'type': 'string'},
                    'banner_imagen': {'type': 'string', 'format': 'binary'},
                    'ubicacion_coordenadas': { 
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'example': 'Point'},
                            'coordinates': {
                                'type': 'array',
                                'items': {'type': 'number'},
                                'example': [-16.4897, -68.1193]
                            }
                        }
                    },
                    'biometric': {'type': 'string'},
                    'negocio': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name_business': {'type': 'string'},
                                'city': {'type': 'string'},
                                'descripcion': {'type': 'string'},
                                'phone': {'type': 'string'},
                                'address': {'type': 'string'},
                                'horario': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'days': {
                                                'type': 'array',
                                                'items': {'type': 'string'}
                                            }
                                        }
                                    }
                                },
                                'openingTime': {'type': 'string'},
                                'closingTime': {'type': 'string'}
                            }
                        }
                    }
                },
                'required': []
            }
        }
       ),
    methods=['POST'], tags=['Negocios'], 
    update=extend_schema(exclude=True),  # Oculta el método PUT (update)
    partial_update=extend_schema(
        tags=['Negocios'],
        summary="Editar mi negocio",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'password': {'type': 'string'},
                    'profile_imagen': {'type': 'string'},
                    'banner_imagen': {'type': 'string'},
                    'ubicacion_coordenadas': { 
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'example': 'Point'},
                            'coordinates': {
                                'type': 'array',
                                'items': {'type': 'number'},
                                'example': [-16.4897, -68.1193]
                            }
                        }
                    },
                    'biometric': {'type': 'string'},
                    'negocio': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name_business': {'type': 'string'},
                                'city': {'type': 'string'},
                                'descripcion': {'type': 'string'},
                                'phone': {'type': 'string'},
                                'address': {'type': 'string'},
                                'horario': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {
                                            'days': {
                                                'type': 'array',
                                                'items': {'type': 'string'}
                                            }
                                        }
                                    }
                                },
                                'openingTime': {'type': 'string'},
                                'closingTime': {'type': 'string'}
                            }
                        }
                    }
                },
                'required': []
            }
        }
    ),
    destroy=extend_schema(tags=['Negocios'],
        summary="Eliminar mi negocio",),
)

class NegocioViewSet(viewsets.ModelViewSet):
    queryset = User.objects.exclude(negocio=None)
    serializer_class = negocioSerializer
    pagination_class = ClientenegocioPagination  # 👈 AQUÍ

    # 1. Indica que el campo de búsqueda es 'id' (el PK de tu modelo User)
    lookup_field = 'id' 
    # 2. Especifica la expresión regular para un ObjectId de 24 caracteres hexadecimales
    lookup_value_regex = '[0-9a-fA-F]{24}' 

    parser_classes = [JSONParser, FormParser, MultiPartParser]

    ##Aqui indico que negocios quiero ver...
    def get_queryset(self):
        user = self.request.user
        
        # Query base: solo negocios activos(que confirmaron su email)
        queryset = User.objects.filter(
            negocio__isnull=False, 
            is_active=True
        ).exclude(negocio=[])

        # aplicamos filtros de búsqueda si hay parámetros
        # el endpoint /business/ soportará ?city=... y ?name_business=... (también ?name)
        # Legacy search parameters
        city_param = self.request.query_params.get('city')
        name_param = self.request.query_params.get('name_business') or self.request.query_params.get('name')
        # single unified term
        q_param = self.request.query_params.get('q')

        if q_param:
            # override the others by treating `q` as search for either field
            city_param = q_param
            name_param = q_param

        # helper to strip accents + lowercase
        def _norm(s: str) -> str:
            if not s:
                return ''
            import unicodedata
            s = unicodedata.normalize('NFD', s)
            return ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn').lower()

        if city_param or name_param:
            # Filtrar en memoria porque el campo `negocio` puede ser
            # un diccionario o una lista de diccionarios.
            filtered = []
            norm_city = _norm(city_param) if city_param else ''
            norm_name = _norm(name_param) if name_param else ''
            for negocio in queryset:
                nb_data = negocio.negocio
                if isinstance(nb_data, list):
                    if len(nb_data) == 0:
                        continue
                    first = nb_data[0]
                elif isinstance(nb_data, dict):
                    first = nb_data
                else:
                    continue

                city_val = _norm(first.get('city', ''))
                name_val = _norm(first.get('name_business', ''))

                if norm_city and norm_city in city_val:
                    filtered.append(negocio)
                    continue
                if norm_name and norm_name in name_val:
                    filtered.append(negocio)
                    continue
            queryset = filtered

        # Ordenar o filtrar según tipo de usuario / ubicación
        action = getattr(self, 'action', None)
        def sort_by_rating(qs):
            """Return list sorted with rated businesses first (highest rating down),
            followed by those lacking any rating.

            The rating is computed from the Comment model (average of all ratings
            left for that business).  None means no ratings have been left yet.
            """
            from api.models import Comment

            def business_rating(user_obj):
                # compute average over comments (may be slow if many users,
                # but dataset is small).  Return None if no ratings exist.
                comments = Comment.objects.filter(negocio_id=user_obj.id)
                if not comments.exists():
                    return None
                total = sum(c.rating for c in comments)
                return round(total / comments.count(), 1)

            with_rating = []
            without_rating = []
            for negocio in qs:
                rat = business_rating(negocio)
                if rat is None:
                    without_rating.append(negocio)
                else:
                    with_rating.append((negocio, rat))
            # sort rated businesses by value descending
            with_rating.sort(key=lambda x: x[1], reverse=True)
            ordered = [n for n, _ in with_rating]
            ordered.extend(without_rating)
            return ordered

        if action == 'list':
            # usuario no autenticado -> por rating
            if not user.is_authenticated:
                return sort_by_rating(queryset)

            # usuario autenticado
            if user.negocio:  # es un negocio
                # Mostrar primero el propio
                own = list(queryset.filter(id=user.id))
                others = list(queryset.exclude(id=user.id))
                # obtener ciudad del propio negocio
                own_city = ''
                if user.negocio and isinstance(user.negocio, list) and len(user.negocio) > 0:
                    own_city = user.negocio[0].get('city', '').lower()

                def city_score(b):
                    cityb = ''
                    if b.negocio and isinstance(b.negocio, list) and len(b.negocio) > 0:
                        cityb = b.negocio[0].get('city', '').lower()
                    if cityb == own_city:
                        return 0
                    if own_city in cityb or cityb in own_city:
                        return 1
                    return 2
                others.sort(key=city_score)
                return own + others

            # es cliente
            if hasattr(user, 'ubicacion_coordenadas') and user.ubicacion_coordenadas:
                # si tiene ciudad guardada (normalizada sin acentos)
                import unicodedata
                def _norm(s: str) -> str:
                    if not s:
                        return ''
                    s = unicodedata.normalize('NFD', s)
                    return ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn').lower()

                user_city = _norm(user.ciudad_coordenadas or '')
                # si no tenemos ciudad pero sí coordenadas, intentar resolverla en el momento
                if not user_city and user.ubicacion_coordenadas:
                    from api.serializers import reverse_geocode_ciudad_coordenadas, _coords_to_lat_lon
                    coords = user.ubicacion_coordenadas.get('coordinates', [])
                    parsed = _coords_to_lat_lon(coords)
                    if parsed:
                        lat, lon = parsed
                        # emular comportamiento del serializer
                        ciudad = reverse_geocode_ciudad_coordenadas(round(float(lat), 5), round(float(lon), 5))
                        if ciudad:
                            user_city = _norm(ciudad)
                            # persistir para no volver a pedirlo cada vez
                            try:
                                user.ciudad_coordenadas = ciudad
                                user.save(update_fields=['ciudad_coordenadas'])
                            except Exception:
                                pass

                # si tras todo lo anterior aún no resolvemos ninguna ciudad, tratamos como sin ubicación
                if not user_city:
                    return sort_by_rating(queryset)

                matching = []
                nonmatching = []
                for negocio in queryset:
                    citybiz = ''
                    if negocio.negocio and isinstance(negocio.negocio, list) and len(negocio.negocio) > 0:
                        citybiz = negocio.negocio[0].get('city', '')
                    citybiz_norm = _norm(citybiz)
                    if user_city and user_city == citybiz_norm:
                        matching.append(negocio)
                    else:
                        nonmatching.append(negocio)

                # ordenar matching por rating descendente, tie-breaker distancia si disponible
                def rating_of(b):
                    if b.negocio and isinstance(b.negocio, list) and len(b.negocio) > 0:
                        return b.negocio[0].get('rating', 0)
                    return 0
                if matching:
                    user_coords = user.ubicacion_coordenadas.get('coordinates', [])
                    if len(user_coords) == 2:
                        u_lng, u_lat = user_coords
                        def rating_dist_key(b):
                            # sort by (-rating, distance)
                            r = -rating_of(b)
                            if b.ubicacion_coordenadas and b.ubicacion_coordenadas.get('coordinates'):
                                coords = b.ubicacion_coordenadas['coordinates']
                                if len(coords) == 2:
                                    d = self.calcular_distancia(u_lat, u_lng, coords[1], coords[0])
                                else:
                                    d = float('inf')
                            else:
                                d = float('inf')
                            return (r, d)
                        matching.sort(key=rating_dist_key)
                    else:
                        matching.sort(key=lambda b: -rating_of(b))

                # ordenamos negocios no coincidentes por distancia si tenemos coords, sino por rating
                user_coords = user.ubicacion_coordenadas.get('coordinates', [])
                if len(user_coords) == 2:
                    u_lng, u_lat = user_coords
                    def dist_rating_key(b):
                        # primary distance, secondary -rating
                        if b.ubicacion_coordenadas and b.ubicacion_coordenadas.get('coordinates'):
                            coords = b.ubicacion_coordenadas['coordinates']
                            if len(coords) == 2:
                                d = self.calcular_distancia(u_lat, u_lng, coords[1], coords[0])
                            else:
                                d = float('inf')
                        else:
                            d = float('inf')
                        r = -rating_of(b)
                        return (d, r)
                    nonmatching.sort(key=dist_rating_key)
                else:
                    nonmatching = sort_by_rating(nonmatching)
                return matching + nonmatching
            else:
                # cliente sin ubicación -> ordenar por rating
                return sort_by_rating(queryset)

        # fuera de list o errores devolver original
        return queryset
                
        
    
    #por si quiero que solamente las mismas negocios vean su info
    #def get_permissions(self):
    #    if self.action == 'create': # Esta linea significa que el endpoint register lo pueda usar cualquiera
    #        return [AllowAny()]  # Permitir registro sin autenticación
    #    elif self.action in ['retrieve', 'partial_update', 'destroy']:  
    #        # Permitir acceso a retrieve, update y destroy solo si el usuario está autenticado
    #       
    #        # Y que el resto de metodos usen IsAuthenticated que significa JWT y el IsSelf que significa
    #        # que el mismo usuario pueda acceder a su propio recurso, ejemplo el usuario 1 solo acceda al endpoint 1 
    #        return [IsAuthenticated(), Minegocio()]  # 👈 Requiere autenticación y que sea el mismo usuario 
    #    #El IsAuthenticated es creado automaticamente por Django, MiUsuario es creado manualmente
    #    return [IsAuthenticated()]


    def get_permissions(self):
        action = getattr(self, 'action', None)

        # permitimos búsquedas públicas junto con list y retrieve
        if action in ['create', 'list', 'retrieve', 'search']:
            return [AllowAny()]
        
        elif action in ['partial_update', 'destroy']:
            # Solo el dueño puede actualizar o eliminar
            return [IsAuthenticated(), Minegocio()]
        return [IsAuthenticated()]
    

    @extend_schema(tags=['Negocio'])
    def create(self, request, *args, **kwargs):
        # Verificar si el usuario ya existe (autenticación social)
        email = request.data.get('email')
        if email and request.user.is_anonymous:
            try:
                existing_user = User.objects.get(email=email)
                # Si el usuario existe y es social, proceder con actualización
                if hasattr(existing_user, 'social_auth'):
                    serializer = self.get_serializer(
                        existing_user, 
                        data=request.data, 
                        partial=True
                    )
                    serializer.is_valid(raise_exception=True)
                    user = serializer.save()
                    
                    return Response(
                        negocioSerializer(user).data, 
                        status=status.HTTP_200_OK
                    )
            except User.DoesNotExist:
                pass

        if request.content_type.startswith("multipart/form-data") or request.content_type.startswith("application/x-www-form-urlencoded"):
            raw_data = querydict_to_nested(request.data)
            data = dict_to_list(raw_data)
        else:
            data = request.data
    
        # 🔑 Normaliza internamente solo dentro de negocio
        negocio = data.get("negocio")
        if negocio:
            if "services" in negocio and isinstance(negocio["services"], dict):
                negocio["services"] = [v for k, v in sorted(negocio["services"].items(), key=lambda x: int(x[0]))]
            if "horario" in negocio and isinstance(negocio["horario"], dict):
                negocio["horario"] = [v for k, v in sorted(negocio["horario"].items(), key=lambda x: int(x[0]))]
                for h in negocio["horario"]:
                    if "days" in h and isinstance(h["days"], dict):
                        h["days"] = [v for k, v in sorted(h["days"].items(), key=lambda x: int(x[0]))]
    
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
    
        signals.user_registered.send(
            sender=self.__class__, user=user, request=self.request
        )
        if djoser_settings.SEND_ACTIVATION_EMAIL:
            context = {"user": user}
            djoser_settings.EMAIL.activation(self.request, context).send([user.email])
    
        return Response(negocioSerializer(user).data, status=status.HTTP_201_CREATED)

        
    def update(self, request, *args, **kwargs):
        if not kwargs.get('partial', False):
            return Response(
                {"detail": "Método PUT no permitido. Use PATCH en su lugar."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED
            )
        return super().update(request, *args, **kwargs)
    
    def partial_update(self, request, *args, **kwargs):
        # 1. Transformar la data de Postman (form-data) a Diccionario anidado
        if request.content_type.startswith("multipart/form-data") or request.content_type.startswith("application/x-www-form-urlencoded"):
            raw_data = querydict_to_nested(request.data)
            data = dict_to_list(raw_data)
        else:
            data = request.data

        # 2. Normalizar el campo negocio si viene como dict (convertir a lista)
        negocio = data.get("negocio")
        if negocio and isinstance(negocio, dict):
            # Esto convierte {'0': {...}} en [{...}]
            data["negocio"] = [v for k, v in sorted(negocio.items(), key=lambda x: int(x[0]))]
            
            # Profundizar en horario y days
            for item in data["negocio"]:
                if "horario" in item and isinstance(item["horario"], dict):
                    item["horario"] = [v for k, v in sorted(item["horario"].items(), key=lambda x: int(x[0]))]
                    for h in item["horario"]:
                        if "days" in h and isinstance(h["days"], dict):
                            h["days"] = [v for k, v in sorted(h["days"].items(), key=lambda x: int(x[0]))]

        kwargs['partial'] = True
        serializer = self.get_serializer(self.get_object(), data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return Response(negocioSerializer(self.get_object()).data)
    
    @extend_schema(
        parameters=[
            
            OpenApiParameter(
                name='city',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='(Opcional) ciudad literal o parcial'
            ),
            OpenApiParameter(
                name='name_business',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='(Opcional) nombre del negocio para filtrar'
            ),
        ],
        tags=['Negocios']
    )
    ##@action(detail=False, methods=['get'], url_path='cercanas')
    ##def negocios_cercanas(self, request):
    ##    """
    ##    Obtener business cercanas a una ubicación
    ##    """
    ##    # Obtener parámetros de la query
    ##    lat = request.query_params.get('lat')
    ##    lng = request.query_params.get('lng')
    ##    radius = float(request.query_params.get('radius', 10))  # Radio default: 10km
    ##    ciudad_coordenadas = request.query_params.get('ciudad_coordenadas')
    ##    
    ##    # Validar parámetros
    ##    if not lat or not lng:
    ##        return Response(
    ##            {"error": "Se requieren parámetros lat y lng"},
    ##            status=status.HTTP_400_BAD_REQUEST
    ##        )
    ##    
    ##    try:
    ##        user_lat = float(lat)
    ##        user_lng = float(lng)
    ##    except ValueError:
    ##        return Response(
    ##            {"error": "Latitud y longitud deben ser números válidos"},
    ##            status=status.HTTP_400_BAD_REQUEST
    ##        )
    ##    
    ##    # Query base: solo business activas
    ##    queryset = User.objects.filter(
    ##        negocio__isnull=False, 
    ##        is_active=True
    ##    ).exclude(negocio=[])
    ##    
    ##    # Filtrar por ciudad si se especifica
    ##    if ciudad_coordenadas:
    ##        queryset = queryset.filter(ciudad_coordenadas__iexact=ciudad_coordenadas)
    ##    
    ##    # Si tenemos coordenadas, calcular distancias
    ##    negocios_con_distancia = []
    ##    
    ##    for negocio in queryset:
    ##        if negocio.location and negocio.location.get('coordinates'):
    ##            negocio_lat, negocio_lng = negocio.location['coordinates']
    ##            
    ##            # Calcular distancia (fórmula Haversine)
    ##            distancia_km = self.calcular_distancia(
    ##                user_lat, user_lng, negocio_lat, negocio_lng
    ##            )
    ##            
    ##            # Solo incluir business dentro del radio
    ##            if distancia_km <= radius:
    ##                negocios_con_distancia.append({
    ##                    'negocio': negocio,
    ##                    'distancia_km': round(distancia_km, 2)
    ##                })
    ##    
    ##    # Ordenar por distancia
    ##    negocios_con_distancia.sort(key=lambda x: x['distancia_km'])
    ##    
    ##    # Paginación
    ##    page = self.paginate_queryset(negocios_con_distancia)
    ##    if page is not None:
    ##        serializer = negocioCercanaSerializer(
    ##            [item['negocio'] for item in page], 
    ##            many=True,
    ##            context={'distancias': {item['negocio'].id: item['distancia_km'] for item in page}}
    ##        )
    ##        return self.get_paginated_response(serializer.data)
    ##    
    ##    serializer = negocioCercanaSerializer(
    ##        [item['negocio'] for item in negocios_con_distancia],
    ##        many=True,
    ##        context={'distancias': {item['negocio'].id: item['distancia_km'] for item in negocios_con_distancia}}
    ##    )
    ##    
    ##    return Response(serializer.data)
    
    @extend_schema(
        tags=['Negocios'],
        summary="Buscar negocios por ciudad o nombre",
        parameters=[
            OpenApiParameter(
                name='q',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Término de búsqueda único que puede coincidir con city o name_business'
            ),
            OpenApiParameter(
                name='city',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='(Opcional) ciudad exacta/parcial'
            ),
            OpenApiParameter(
                name='name_business',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='(Opcional) nombre del negocio'
            ),
        ]
    )
    @action(detail=False, methods=['get'], url_path='search', permission_classes=[AllowAny])
    def search(self, request):
        """Retorna una lista paginada de negocios filtrados por `city` o `name_business`.
        
        Parámetros de consulta aceptados:
        - `q`: término único usado para buscar en ambos campos
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def calcular_distancia(self, lat1, lng1, lat2, lng2):
        """Calcula distancia entre dos puntos usando fórmula Haversine"""
        
        R = 6371  # Radio de la Tierra en km
        
        lat1_rad = radians(lat1)
        lng1_rad = radians(lng1)
        lat2_rad = radians(lat2)
        lng2_rad = radians(lng2)
        
        dlng = lng2_rad - lng1_rad
        dlat = lat2_rad - lat1_rad
        
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
        
###################################3333333#Comentariose###############################################

@extend_schema_view(
    list=extend_schema(
        tags=['Comentarios'],
        summary="Obtener todos los comentarios",
        ),
    retrieve=extend_schema(
        #Retrieve son las consultas Get con ID
        tags=['Comentarios'], 
        summary="Obtener un comentario en especifico",
        ),
    create=extend_schema(
        tags=['Comentarios'],
        summary="Crear comentario para una negocio",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'negocio_id': {'type': 'string'},
                    'rating': {'type': 'number'},
                    'description': {'type': 'string'},
                },
                'required': []
            }
        }
    ), 
    methods=['POST'], tags=['Comentarios'], 
    update=extend_schema(exclude=True),  # Oculta el método PUT (update)
    partial_update=extend_schema(
        tags=['Comentarios'],
        summary="Editar mi comentario",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'negocio_id': {'type': 'string'},
                    'rating': {'type': 'number'},
                    'description': {'type': 'string'},
                },
                'required': []
            }
        }
    ),   
    destroy=extend_schema(tags=['Comentarios'], 
        summary="Eliminar mi comentario",
        ),
)

class ComentarioViewSet(viewsets.ModelViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    pagination_class = ComentarioPagination  

    lookup_field = 'id'
    lookup_value_regex = '[0-9a-fA-F]{24}' 

    def get_permissions(self):
        action = getattr(self, 'action', None)

        # listado público y detalle de comentario siempre permitidos
        if action in ['list', 'retrieve', 'negocio_comments']:
            return [AllowAny()]
        
        # mis comentarios requiere autenticación
        if action == 'my_comments':
            return [IsAuthenticated()]
        
        elif action in ['create', 'partial_update', 'destroy']:
            # crear, editar y borrar sólo si está autenticado (own objects check in serializer or view)
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=['Comentarios'],
        summary="Obtener mis comentarios",
        description="Retorna todos los comentarios que el usuario autenticado ha realizado",
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='mis-comentarios')
    def my_comments(self, request):
        """Devuelve todos los comentarios realizados por el usuario autenticado."""
        qs = self.get_queryset().filter(cliente=request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=['Comentarios'],
        summary="Comentarios por negocio",
        description="Devuelve todos los comentarios asociados a un negocio específico. Se pasa el id del negocio como query param `negocio_id` o `business_id`.",
        parameters=[
            OpenApiParameter(name='negocio_id', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, description='ID del negocio'),
        ],
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='negocio')
    def negocio_comments(self, request):
        """Lista comentarios para un negocio específico mediante query param `negocio_id` o `business_id`."""
        negocio_id = request.query_params.get('negocio_id') or request.query_params.get('business_id')
        if not negocio_id:
            return Response({"detail": "Se requiere parámetro negocio_id"}, status=status.HTTP_400_BAD_REQUEST)
        qs = self.get_queryset().filter(negocio__id=negocio_id)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
  
##########################Servicios

@extend_schema_view(
    list=extend_schema(
        tags=['Servicios'],
        summary="Obtener todos los servicios que he publicado",
        ),
    retrieve=extend_schema(
        #Retrieve son las consultas Get con ID
        tags=['Servicios'], 
        summary="Obtener un servicio en especifico",
        ),
    create=extend_schema(
        tags=['Servicios'],
        summary="Publicar servicios de mi negocio",
        request=ServicioSerializer, 
    ), 
    methods=['POST'], tags=['Servicios'], 
    update=extend_schema(exclude=True),  # Oculta el método PUT (update)
    partial_update=extend_schema(
        tags=['Servicios'],
        summary="Editar mi servicio",
    ),   
    destroy=extend_schema(tags=['Servicios'], 
        summary="Eliminar mi servicio",
        ),
)

class ServicioViewSet(viewsets.ModelViewSet):
    queryset = Servicio.objects.all()
    serializer_class = ServicioSerializer
    pagination_class = ServicioPagination
    permission_classes = [IsAuthenticated]

    lookup_field = 'id'
    lookup_value_regex = '[0-9a-fA-F]{24}' 


    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options'] # Excluye 'put'

    @extend_schema(
        summary="Obtener todos los servicios de un negocio específico",
        #description="Lista todos los comentarios para un negocio dada por su ID.",
        parameters=[
            {
                "name": "business_id",
                "type": "string",
                "required": True,
                #"description": "ID de el negocio",
                "in": "path"
            }
        ],
        tags=['Servicios'] # Asegúrate de que tenga el mismo tag para agrupar
    )
    # --- NUEVA ACCIÓN PERSONALIZADA PARA SERVICIOS DE LOS negocioS ---
    @action(detail=False, methods=['get'], url_path='negocio/(?P<business_id>[0-9a-fA-F]{24})')
    def by_negocio(self, request, business_id=None):
        """
        Obtener todos los servicios de un negocio específica
        """
        try:
            negocio_instance = User.objects.get(id=business_id, negocio__isnull=False)
            servicios = Servicio.objects.filter(negocio=negocio_instance)

            # 🔥 APLICAR PAGINACIÓN aquí
            page = self.paginate_queryset(servicios)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            # Si no hay paginación, devolver todos (fallback)

            serializer = self.get_serializer(servicios, many=True)
            return Response(serializer.data)
        except (User.DoesNotExist, ValueError):
            raise Http404("negocio no encontrado o ID inválido.")

    def perform_create(self, serializer):
        serializer.save(negocio=self.request.user)  # negocio autenticado


    def get_object(self):
        obj = super().get_object()
        self.check_object_permissions(self.request, obj)
        return obj


    def get_permissions(self):
        action = getattr(self, 'action', None)

        if action in ['list', 'retrieve', 'by_negocio']:
                return [AllowAny()]
            
        elif action in ['create', 'partial_update', 'destroy']:
            # Permitir que cualquier usuario autenticado pueda modificar su propio comentario 
            return [IsAuthenticated(), MiServicio()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer) # This calls serializer.save()
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)



class ChatWebsocketInfoView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        description='Información para conectarse al websocket de chat. Use JWT como query param `token`.',
        responses={
            200: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request, *args, **kwargs):
        scheme = 'wss' if request.is_secure() else 'ws'
        host = request.get_host()
        websocket_template = f"{scheme}://{host}/ws/chat/<receptor_id>/?token=<JWT>"

        return Response({
            'websocket_url': websocket_template,
            'description': 'Conéctese a esta URL usando el ID del destinatario. Envíe el JWT como query param `token=<JWT>`.',
            'message_format': {
                'message': 'Texto del mensaje'
            },
            'broadcast_event': {
                'message': 'Texto del mensaje',
                'emisor': '<user_id>',
                'receptor': '<receptor_id>',
                'hora_mensaje': '<ISO8601>'
            }
        })

@extend_schema_view(
    list=extend_schema(
        tags=['Chat'],
        summary="Obtener todos los mensajes relacionados con el usuario autenticado",
        ),
    retrieve=extend_schema(
        #Retrieve son las consultas Get con ID
        tags=['Chat'], 
        summary="Obtener un mensaje en especifico",
        ),
    create=extend_schema(
        tags=['Chat'],
        summary="Enviar un mensaje",
        request=ChatMessageSerializer, 
    ), 
    methods=['POST'], tags=['Chat'], 
    update=extend_schema(exclude=True),  # Oculta el método PUT (update)
    partial_update=extend_schema(
        tags=['Chat'],
        summary="Editar mi mensaje",
    ),   
    destroy=extend_schema(tags=['Chat'], 
        summary="Eliminar mi mensaje",
        ),
)

class ChatMessageViewSet(viewsets.ModelViewSet):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated, ChatMessageParticipantPermission]

    def get_queryset(self):
        user = self.request.user
        queryset = ChatMessage.objects.filter(Q(emisor=user) | Q(receptor=user))
        other_user_id = self.request.query_params.get('other_user_id')
        if other_user_id:
            queryset = queryset.filter(
                Q(emisor_id=other_user_id, receptor=user) |
                Q(emisor=user, receptor_id=other_user_id)
            )
        return queryset.order_by('-hora_mensaje')

    def list(self, request, *args, **kwargs):
        user = request.user
        queryset = self.filter_queryset(self.get_queryset())

        unread = queryset.filter(receptor=user, visto=False)
        if unread.exists():
            unread.update(visto=True)

        grouped = {}
        for message in queryset.order_by('-hora_mensaje'):
            other = message.receptor if message.emisor == user else message.emisor
            if other is None:
                continue

            # sólo agrupar conversaciones con un business o si el usuario actual es business
            if not _is_business_user(other) and not _is_business_user(user):
                continue

            key = str(other.id)
            if key not in grouped:
                grouped[key] = {
                    'emisor': self._serialize_chat_user(user),
                    'receptor': self._serialize_chat_user(other),
                    'chat': []
                }

            chat_item = {
                'id': str(message.id),
                'mensaje_texto': message.mensaje_texto,
                'hora_mensaje': message.hora_mensaje.isoformat(),
                'typeuser': 'emisor' if message.emisor == user else 'receptor',
            }
            if message.emisor == user:
                chat_item['visto'] = message.visto

            grouped[key]['chat'].append(chat_item)

        grouped_list = list(grouped.values())

        page = self.paginate_queryset(grouped_list)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(grouped_list)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.receptor == request.user and not instance.visto:
            instance.visto = True
            instance.save(update_fields=['visto'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Obtener todos los mensajes recibidos por o enviados a un usuario específico",
        #description="Lista todos los comentarios para un negocio dada por su ID.",
        parameters=[
            {
                "name": "emisor_id",
                "type": "string",
                "required": True,
                #"description": "ID de el negocio",
                "in": "path"
            }
        ],
        tags=['Chat'] # Asegúrate de que tenga el mismo tag para agrupar
    )
    @action( detail=False, methods=['get'], url_path='emisor/(?P<emisor_id>[^/.]+)', permission_classes=[IsAuthenticated])
    def emisor(self, request, emisor_id=None):
        user = request.user
        try:
            other_user = User.objects.get(id=emisor_id)
        except (User.DoesNotExist, ValueError):
            raise Http404("Usuario no encontrado o ID inválido.")

        messages = ChatMessage.objects.filter(
            Q(emisor_id=emisor_id, receptor=user) |
            Q(emisor=user, receptor_id=emisor_id)
        ).order_by('-hora_mensaje')

        unread = messages.filter(receptor=request.user, visto=False)
        if unread.exists():
            unread.update(visto=True)

        chat = []
        for message in messages:
            item = {
                'id': str(message.id),
                'mensaje_texto': message.mensaje_texto,
                'hora_mensaje': message.hora_mensaje.isoformat(),
                'typeuser': 'emisor' if message.emisor == request.user else 'receptor',
            }
            if message.emisor == request.user:
                item['visto'] = message.visto
            chat.append(item)

        return Response([
            {
                'emisor': self._serialize_chat_user(user),
                'receptor': self._serialize_chat_user(other_user),
                'chat': chat,
            }
        ])

    @extend_schema(
        summary="Obtener resumen de conversaciones con el último mensaje",
        tags=['Chat'],
    )
    @action(detail=False, methods=['get'], url_path='conversations', permission_classes=[IsAuthenticated])
    def conversations(self, request):
        user = request.user
        queryset = self.filter_queryset(self.get_queryset())

        last_conversations = {}
        for message in queryset.order_by('-hora_mensaje'):
            other = message.receptor if message.emisor == user else message.emisor
            if other is None:
                continue

            if not _is_business_user(other) and not _is_business_user(user):
                continue

            key = str(other.id)
            if key in last_conversations:
                continue

            ultimo_mensaje = {
                'mensaje_texto': message.mensaje_texto,
                'hora_mensaje': message.hora_mensaje.isoformat(),
            }
            last_conversations[key] = {
                'receptor': self._serialize_chat_user(other),
                'ultimo_mensaje': ultimo_mensaje,
            }

        result = list(last_conversations.values())
        page = self.paginate_queryset(result)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(result)

    def _serialize_chat_user(self, user):
        if user is None:
            return None

        data = {
            'id': str(user.id),
            'profile_imagen': self._get_media_url(user.profile_imagen),
        }

        negocio = getattr(user, 'negocio', None)
        if negocio:
            name_business = ''
            if isinstance(negocio, list) and len(negocio) > 0:
                name_business = negocio[0].get('name_business', '') or ''
            elif isinstance(negocio, dict):
                name_business = negocio.get('name_business', '') or ''
            data['name_business'] = name_business
        else:
            data['username'] = str(user.username) if getattr(user, 'username', None) else ''

        return data

    def _get_media_url(self, media_field):
        if not media_field:
            return None
        try:
            return media_field.url
        except Exception:
            return str(media_field)

    def perform_create(self, serializer):
        serializer.save(emisor=self.request.user)


###################################3333333#LOGIN###############################################
@extend_schema(tags=['Login'], summary="Iniciar sesion",)
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        
        if not user.is_active:
            return Response(
                {"detail": "Tu cuenta no esta activa porque no has confirmado tu email. Por favor, revisa tu correo electrónico para activarla."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # ----------------------------------
        
        # Generar tokens
        refresh = RefreshToken.for_user(user)
        
        # Determinar tipo de usuario
        tipo_usuario = "negocio" if user.negocio else "cliente"
        
        return Response({
            'refresh': str(refresh),
            'token': str(refresh.access_token),
            'id': str(user.id),
            'tipo_usuario': tipo_usuario,
        }, status=status.HTTP_200_OK)

###################################3333333#TOKEN##############################################
@extend_schema(tags=['Token'], request=RefreshTokenSerializer, summary="Reiniciar token",)
class TokenRefreshView(generics.GenericAPIView):
    serializer_class = RefreshTokenSerializer  # 👈 Serializador creado manualmente


    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh = serializer.validated_data.get('refresh')

        if refresh:
            try:
                token = RefreshToken(refresh)
                access_token = token.access_token
                return Response({'token': str(access_token)}, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({'error': 'Token inválido'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'Se requiere el token de refresco'}, status=status.HTTP_400_BAD_REQUEST)



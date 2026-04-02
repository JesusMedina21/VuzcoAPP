from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class DynamicPageNumberPagination(PageNumberPagination):
    page_size_query_param = 'limit'  # El parámetro que usará el frontend
    max_page_size = 100  # Límite máximo para prevenir abusos
    
    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            'count': self.page.paginator.count,
            'page_size': self.page_size,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data
        })

class ClientenegocioPagination(DynamicPageNumberPagination):
    page_size = 20  # Default para clientes y negocios

class ComentarioPagination(DynamicPageNumberPagination):
    page_size = 20  # Default para comentarios

class ServicioPagination(DynamicPageNumberPagination):
    page_size = 6  # Default para servicios
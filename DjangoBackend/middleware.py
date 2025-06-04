# middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.db import connections

class DatabaseRouterMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.path.startswith('/tsl/'):
            connections['default'].set_alias('tsl_db')
        elif request.path.startswith('/api/'):
            connections['default'].set_alias('default')
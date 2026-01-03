"""
Middleware to attach Supabase user context to requests
"""
from django.utils.deprecation import MiddlewareMixin


class SupabaseAuthMiddleware(MiddlewareMixin):
    """
    Middleware that attaches tenant_id to request for RLS
    """
    
    def process_request(self, request):
        # If user is authenticated via SupabaseAuthentication
        if hasattr(request, 'user') and hasattr(request.user, 'tenant_id'):
            request.tenant_id = request.user.tenant_id
            request.user_id = request.user.user_id
        else:
            request.tenant_id = None
            request.user_id = None
        
        return None

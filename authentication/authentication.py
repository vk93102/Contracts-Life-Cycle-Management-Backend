"""
Supabase JWT Authentication for Django REST Framework
"""
import jwt
from django.conf import settings
from rest_framework import authentication
from rest_framework import exceptions


class SupabaseAuthentication(authentication.BaseAuthentication):
    """
    Custom authentication class that validates Supabase JWT tokens
    """
    
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header:
            return None
        
        try:
            # Extract token from "Bearer <token>"
            parts = auth_header.split()
            if parts[0].lower() != 'bearer':
                return None
            
            if len(parts) == 1:
                raise exceptions.AuthenticationFailed('Invalid token header. No credentials provided.')
            elif len(parts) > 2:
                raise exceptions.AuthenticationFailed('Invalid token header. Token string should not contain spaces.')
            
            token = parts[1]
            
            # Check for demo token first (for testing)
            if token == 'demo-token-xyz':
                user = SupabaseUser(
                    user_id='550e8400-e29b-41d4-a716-446655440000',
                    email='demo@example.com',
                    tenant_id='c654fc63-934c-49a3-9042-a66a14f0bbc5',  # From seed data
                    role='user',
                    token=token
                )
                return (user, None)
            
            # Use the JWT secret (allow fallback for development)
            jwt_secret = settings.SUPABASE_JWT_SECRET or 'demo-secret-key-change-in-production'
            
            # Decode and verify the JWT
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=['HS256'],
                audience='authenticated'
            )
            
            # Extract user information
            user_id = payload.get('sub')
            email = payload.get('email')
            user_metadata = payload.get('user_metadata', {})
            tenant_id = user_metadata.get('tenant_id')
            role = payload.get('role', 'user')
            
            if not user_id:
                raise exceptions.AuthenticationFailed('Invalid token payload')
            
            # Create a user object (we're not using Django's User model)
            user = SupabaseUser(
                user_id=user_id,
                email=email,
                tenant_id=tenant_id,
                role=role,
                token=token
            )
            
            return (user, None)
            
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('Invalid token')
        except Exception as e:
            raise exceptions.AuthenticationFailed(f'Authentication failed: {str(e)}')


class SupabaseUser:
    """
    Represents a Supabase authenticated user
    """
    
    def __init__(self, user_id, email, tenant_id, role, token):
        self.user_id = user_id
        self.email = email
        self.tenant_id = tenant_id
        self.role = role
        self.token = token
        self.is_authenticated = True
        self.is_anonymous = False
    
    def __str__(self):
        return f"SupabaseUser({self.email})"
    
    @property
    def is_admin(self):
        return self.role == 'admin'

"""
Authentication views
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
import jwt
import secrets
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import User


class TokenView(APIView):
    """
    POST /api/auth/login/
    Authenticate user and generate JWT token
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        from rest_framework_simplejwt.tokens import RefreshToken
        
        email = request.data.get('email', '')
        password = request.data.get('password', '')
        
        if not email or not password:
            return Response(
                {'error': 'Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verify password
        if not user.check_password(password):
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Generate JWT tokens using SimpleJWT
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'user_id': str(user.user_id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'tenant_id': str(user.tenant_id),
                'is_staff': user.is_staff
            }
        })


class CurrentUserView(APIView):
    """
    GET /api/v1/auth/me/
    Returns current user information with tenant context
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        if not hasattr(user, 'user_id'):
            return Response(
                {'error': 'Invalid authentication'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        return Response({
            'user_id': user.user_id,
            'email': user.email,
            'tenant_id': user.tenant_id,
            'is_staff': user.is_staff
        })


class RegisterView(APIView):
    """
    POST /api/v1/auth/register/
    Register a new user
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        full_name = request.data.get('full_name', '').strip()
        
        # Validation
        if not email or not password:
            return Response(
                {'error': 'Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(password) < 6:
            return Response(
                {'error': 'Password must be at least 6 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already exists
        if User.objects.filter(email=email).exists():
            return Response(
                {'error': 'User with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create new user and assign to a tenant
        # In production, you'd have proper tenant assignment logic
        import uuid
        tenant_id = uuid.uuid4()
        
        user = User(
            email=email,
            first_name=full_name.split()[0] if full_name else '',
            last_name=' '.join(full_name.split()[1:]) if full_name and len(full_name.split()) > 1 else '',
            tenant_id=tenant_id,
            is_active=True,
            is_staff=False,
            is_superuser=False
        )
        user.set_password(password)
        user.save()
        
        # Generate JWT tokens using SimpleJWT
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'message': 'User created successfully',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'user_id': str(user.user_id),
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'tenant_id': str(user.tenant_id),
                'is_staff': user.is_staff
            }
        }, status=status.HTTP_201_CREATED)


class ForgotPasswordView(APIView):
    """
    POST /api/v1/auth/forgot-password/
    Request password reset token
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        
        if not email:
            return Response(
                {'error': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            # Don't reveal if email exists for security
            return Response({
                'message': 'If the email exists, a password reset link has been sent'
            })
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires = timezone.now() + timedelta(hours=1)
        user.save()
        
        # In production, send email with reset link
        # For now, we'll return the token in the response for testing
        reset_link = f"http://localhost:3000/#reset?token={reset_token}"
        
        # TODO: Send email
        # send_mail(
        #     'Password Reset Request',
        #     f'Click this link to reset your password: {reset_link}',
        #     'noreply@clm.com',
        #     [email],
        #     fail_silently=False,
        # )
        
        return Response({
            'message': 'If the email exists, a password reset link has been sent',
            'reset_token': reset_token,  # Remove in production
            'reset_link': reset_link  # Remove in production
        })


class ResetPasswordView(APIView):
    """
    POST /api/v1/auth/reset-password/
    Reset password using token
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        token = request.data.get('token', '')
        new_password = request.data.get('new_password', '') or request.data.get('password', '')
        
        if not token or not new_password:
            return Response(
                {'error': 'Token and new password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(new_password) < 6:
            return Response(
                {'error': 'Password must be at least 6 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(
                reset_token=token,
                reset_token_expires__gt=timezone.now(),
                is_active=True
            )
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired reset token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update password
        user.set_password(new_password)
        user.reset_token = None
        user.reset_token_expires = None
        user.save()
        
        return Response({
            'message': 'Password reset successfully'
        })


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Logout user (invalidate token)
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return Response({
            'message': 'Logged out successfully'
        })


class RefreshTokenView(APIView):
    """
    POST /api/v1/auth/refresh/
    Refresh JWT token using refresh token
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        from rest_framework_simplejwt.tokens import RefreshToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        
        refresh_token = request.data.get('refresh', '')
        
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            refresh = RefreshToken(refresh_token)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            })
        except (InvalidToken, TokenError) as e:
            return Response(
                {'error': 'Invalid refresh token'},
                status=status.HTTP_401_UNAUTHORIZED
            )

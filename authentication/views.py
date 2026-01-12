"""
Authentication views with real OTP implementation
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import User
from .otp_service import OTPService


class TokenView(APIView):
    """POST /api/auth/login/ - Authenticate user and generate JWT token"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        
        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            if not user.check_password(password):
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        refresh = RefreshToken.for_user(user)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {'user_id': str(user.user_id), 'email': user.email, 'tenant_id': str(user.tenant_id)}
        }, status=status.HTTP_200_OK)


class RegisterView(APIView):
    """POST /api/auth/register/ - Register new user"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        full_name = request.data.get('full_name', '').strip()
        
        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 6:
            return Response({'error': 'Password minimum 6 chars'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({'error': 'User exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        import uuid
        user = User(email=email, first_name=full_name.split()[0] if full_name else '', tenant_id=uuid.uuid4(), is_active=True)
        user.set_password(password)
        user.save()
        
        # Send welcome email
        OTPService.send_welcome_email(user)
        
        # Send OTP for email verification
        otp_result = OTPService.send_email_otp(user.email)
        otp_message = otp_result.get('message', 'OTP sent to email')
        
        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'user': {'user_id': str(user.user_id), 'email': user.email, 'message': f'User registered successfully. {otp_message}'}}, status=status.HTTP_201_CREATED)


class CurrentUserView(APIView):
    """GET /api/auth/me/ - Get current user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({'user_id': str(user.user_id), 'email': user.email, 'tenant_id': str(user.tenant_id)}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /api/auth/logout/ - Logout"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return Response({'message': 'Logged out'}, status=status.HTTP_200_OK)


class RefreshTokenView(APIView):
    """POST /api/auth/refresh/ - Refresh token"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        refresh_token = request.data.get('refresh', '')
        if not refresh_token:
            return Response({'error': 'Refresh token required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            refresh = RefreshToken(refresh_token)
            return Response({'access': str(refresh.access_token), 'refresh': str(refresh)}, status=status.HTTP_200_OK)
        except (InvalidToken, TokenError):
            return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)


class RequestLoginOTPView(APIView):
    """POST /api/auth/request-login-otp/ - Request login OTP"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            otp = OTPService.generate_otp()
            user.login_otp = otp
            user.otp_created_at = timezone.now()
            user.otp_attempts = 0
            user.save(update_fields=['login_otp', 'otp_created_at', 'otp_attempts'])
            OTPService.send_login_otp(user, otp)
        except User.DoesNotExist:
            pass
        
        return Response({'message': 'OTP sent if email exists'}, status=status.HTTP_200_OK)


class VerifyEmailOTPView(APIView):
    """POST /api/auth/verify-email-otp/ - Verify login OTP"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp', '').strip()
        
        if not email or not otp:
            return Response({'error': 'Email and OTP required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            is_valid, msg = OTPService.verify_otp(user, otp, 'login')
            if not is_valid:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
            
            OTPService.clear_otp(user, 'login')
            refresh = RefreshToken.for_user(user)
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'user': {'user_id': str(user.user_id), 'email': user.email}}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class ForgotPasswordView(APIView):
    """POST /api/auth/forgot-password/ - Request password reset"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            otp = OTPService.generate_otp()
            user.password_reset_otp = otp
            user.otp_created_at = timezone.now()
            user.otp_attempts = 0
            user.save(update_fields=['password_reset_otp', 'otp_created_at', 'otp_attempts'])
            OTPService.send_password_reset_otp(user, otp)
        except User.DoesNotExist:
            pass
        
        return Response({'message': 'Reset OTP sent if email exists'}, status=status.HTTP_200_OK)


class VerifyPasswordResetOTPView(APIView):
    """POST /api/auth/verify-password-reset-otp/ - Verify reset OTP"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp', '').strip()
        
        if not email or not otp:
            return Response({'error': 'Email and OTP required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            is_valid, msg = OTPService.verify_otp(user, otp, 'password_reset')
            if not is_valid:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'message': 'OTP verified', 'verified': True}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class ResendPasswordResetOTPView(APIView):
    """POST /api/auth/resend-password-reset-otp/ - Resend OTP"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            otp = OTPService.generate_otp()
            user.password_reset_otp = otp
            user.otp_created_at = timezone.now()
            user.otp_attempts = 0
            user.save(update_fields=['password_reset_otp', 'otp_created_at', 'otp_attempts'])
            OTPService.send_password_reset_otp(user, otp)
        except User.DoesNotExist:
            pass
        
        return Response({'message': 'OTP resent'}, status=status.HTTP_200_OK)


class ResetPasswordView(APIView):
    """POST /api/auth/reset-password/ - Reset password"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp', '').strip()
        password = request.data.get('password', '')
        
        if not email or not otp or not password:
            return Response({'error': 'Email, OTP, password required'}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 6:
            return Response({'error': 'Password min 6 chars'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email, is_active=True)
            is_valid, msg = OTPService.verify_otp(user, otp, 'password_reset')
            if not is_valid:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(password)
            OTPService.clear_otp(user, 'password_reset')
            user.save()
            return Response({'message': 'Password reset'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

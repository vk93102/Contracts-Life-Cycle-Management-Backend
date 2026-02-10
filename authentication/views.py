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
from tenants.models import TenantModel
import uuid


class TokenView(APIView):
    """POST /api/auth/login/ - Authenticate user and generate JWT token"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        
        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        # OTP-gated signup: if credentials are correct but account is inactive,
        # resend verification OTP and prompt the client to verify.
        if not user.is_active:
            otp = OTPService.generate_otp()
            user.login_otp = otp
            user.otp_created_at = timezone.now()
            user.otp_attempts = 0
            user.save(update_fields=['login_otp', 'otp_created_at', 'otp_attempts'])
            OTPService.send_login_otp(user, otp)
            return Response(
                {
                    'error': 'Account not verified. OTP sent to email.',
                    'pending_verification': True,
                    'email': user.email,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        refresh = RefreshToken.for_user(user)
        # Embed commonly needed claims so downstream requests don't require a DB lookup.
        is_admin = bool(user.is_staff or user.is_superuser)
        is_superadmin = bool(user.is_superuser)
        refresh['email'] = user.email
        refresh['tenant_id'] = str(user.tenant_id)
        refresh['is_admin'] = is_admin
        refresh['is_superadmin'] = is_superadmin
        access = refresh.access_token
        access['email'] = user.email
        access['tenant_id'] = str(user.tenant_id)
        access['is_admin'] = is_admin
        access['is_superadmin'] = is_superadmin
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'user': {
                'user_id': str(user.user_id),
                'email': user.email,
                'tenant_id': str(user.tenant_id),
                'is_admin': is_admin,
                'is_superadmin': is_superadmin,
            }
        }, status=status.HTTP_200_OK)


class RegisterView(APIView):
    """POST /api/auth/register/ - Register new user"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        full_name = request.data.get('full_name', '').strip()
        company = request.data.get('company', '').strip()
        tenant_id_raw = (request.data.get('tenant_id') or '').strip()
        tenant_domain = (request.data.get('tenant_domain') or '').strip().lower()
        
        if not email or not password:
            return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 6:
            return Response({'error': 'Password minimum 6 chars'}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({'error': 'User exists'}, status=status.HTTP_400_BAD_REQUEST)

        tenant_id = None
        if tenant_id_raw:
            try:
                tenant_id = uuid.UUID(tenant_id_raw)
            except ValueError:
                return Response({'error': 'Invalid tenant_id'}, status=status.HTTP_400_BAD_REQUEST)

        if tenant_id is None and tenant_domain:
            tenant = TenantModel.objects.filter(domain=tenant_domain).first()
            if tenant:
                tenant_id = tenant.id

        if tenant_id is None:
            email_domain = (email.split('@', 1)[1] if '@' in email else '').strip().lower()
            if email_domain:
                tenant = TenantModel.objects.filter(domain=email_domain).first()
                if tenant:
                    tenant_id = tenant.id

        if tenant_id is None:
            # Default to first active tenant if one exists (single-tenant friendly).
            tenant = TenantModel.objects.filter(status='active').order_by('created_at').first()
            if tenant:
                tenant_id = tenant.id

        if tenant_id is None:
            # Last resort: create a new tenant inferred from email domain.
            email_domain = (email.split('@', 1)[1] if '@' in email else 'tenant.local').strip().lower() or 'tenant.local'
            base_domain = email_domain
            domain = base_domain
            suffix = 1
            while TenantModel.objects.filter(domain=domain).exists():
                suffix += 1
                domain = f"{base_domain}-{suffix}"
            tenant = TenantModel.objects.create(
                name=f"Tenant {domain}",
                domain=domain,
                status='active',
                subscription_plan='free',
            )
            tenant_id = tenant.id

        user = User(
            email=email,
            first_name=full_name.split()[0] if full_name else '',
            tenant_id=tenant_id,
            is_active=False,
        )
        user.set_password(password)
        user.save()

        # Send OTP for email verification (account remains inactive until verified)
        otp_result = OTPService.send_email_otp(user.email)
        otp_message = otp_result.get('message', 'OTP sent to email')

        # Optionally, store company info via tenant name for new tenants (best-effort).
        # This avoids schema changes while capturing the organization label for signup.
        if company and tenant_id:
            try:
                tenant = TenantModel.objects.filter(id=tenant_id).first()
                if tenant and (tenant.name.startswith('Tenant ') or tenant.name == tenant.domain):
                    tenant.name = company
                    tenant.save(update_fields=['name'])
            except Exception:
                pass

        return Response({
            'message': f'Registration started. {otp_message}',
            'pending_verification': True,
            'email': user.email,
        }, status=status.HTTP_201_CREATED)


class CurrentUserView(APIView):
    """GET /api/auth/me/ - Get current user"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        # Works for both DB-backed User and stateless JWTClaimsUser.
        user_id = getattr(user, 'user_id', None) or getattr(user, 'pk', None) or ''
        email = getattr(user, 'email', None)
        tenant_id = getattr(user, 'tenant_id', None)
        is_admin = bool(
            getattr(user, 'is_admin', False)
            or getattr(user, 'is_staff', False)
            or getattr(user, 'is_superuser', False)
        )
        is_superadmin = bool(
            getattr(user, 'is_superadmin', False)
            or getattr(user, 'is_superuser', False)
        )
        return Response({
            'user_id': str(user_id),
            'email': email,
            'tenant_id': str(tenant_id) if tenant_id is not None else None,
            'is_admin': is_admin,
            'is_superadmin': is_superadmin,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /api/auth/logout/ - Logout"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        return Response({'message': 'Logged out'}, status=status.HTTP_200_OK)


class RefreshTokenView(APIView):
    """POST /api/auth/refresh/ - Refresh token"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
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
    throttle_scope = 'auth'
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Used for both login-OTP and email verification resend.
            user = User.objects.get(email=email)
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
    throttle_scope = 'auth'
    
    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        otp = request.data.get('otp', '').strip()
        
        if not email or not otp:
            return Response({'error': 'Email and OTP required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Allow verifying OTP for newly-registered (inactive) users as well.
            user = User.objects.get(email=email)
            is_valid, msg = OTPService.verify_otp(user, otp, 'login')
            if not is_valid:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

            # Activate user on successful email verification.
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])
                OTPService.send_welcome_email(user)

            OTPService.clear_otp(user, 'login')
            refresh = RefreshToken.for_user(user)
            is_admin = bool(user.is_staff or user.is_superuser)
            is_superadmin = bool(user.is_superuser)
            refresh['email'] = user.email
            refresh['tenant_id'] = str(user.tenant_id)
            refresh['is_admin'] = is_admin
            refresh['is_superadmin'] = is_superadmin
            access = refresh.access_token
            access['email'] = user.email
            access['tenant_id'] = str(user.tenant_id)
            access['is_admin'] = is_admin
            access['is_superadmin'] = is_superadmin
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            
            return Response({
                'access': str(access),
                'refresh': str(refresh),
                'user': {
                    'user_id': str(user.user_id),
                    'email': user.email,
                    'tenant_id': str(user.tenant_id),
                    'is_admin': is_admin,
                    'is_superadmin': is_superadmin,
                }
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class ForgotPasswordView(APIView):
    """POST /api/auth/forgot-password/ - Request password reset"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
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
    throttle_scope = 'auth'
    
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
    throttle_scope = 'auth'
    
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
    throttle_scope = 'auth'
    
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

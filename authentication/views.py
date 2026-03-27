"""
Authentication views with real OTP implementation
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from drf_spectacular.utils import extend_schema
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import User
from .otp_service import OTPService
from tenants.models import TenantModel

from .openapi_serializers import (
    ForgotPasswordRequestSerializer,
    GoogleLoginRequestSerializer,
    LoginRequestSerializer,
    LoginResponseSerializer,
    MessageResponseSerializer,
    RefreshTokenRequestSerializer,
    RefreshTokenResponseSerializer,
    RegisterRequestSerializer,
    RegisterResponseSerializer,
    RequestOTPRequestSerializer,
    ResetPasswordRequestSerializer,
    UserContextSerializer,
    VerifyEmailOTPRequestSerializer,
    VerifyEmailOTPResponseSerializer,
    VerifyPasswordResetOTPRequestSerializer,
    VerifyPasswordResetOTPResponseSerializer,
)
import uuid
import os
import logging

try:
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests
except Exception:  # pragma: no cover
    google_id_token = None
    google_requests = None


logger = logging.getLogger(__name__)


def _resolve_tenant_id_for_email(email: str):
    tenant_id = None

    email_domain = (email.split('@', 1)[1] if '@' in email else '').strip().lower()
    if email_domain:
        tenant = TenantModel.objects.filter(domain=email_domain).first()
        if tenant:
            tenant_id = tenant.id

    if tenant_id is None:
        tenant = TenantModel.objects.filter(status='active').order_by('created_at').first()
        if tenant:
            tenant_id = tenant.id

    if tenant_id is None:
        base_domain = email_domain or 'tenant.local'
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

    return tenant_id


def _bootstrap_admin_if_enabled(user: User) -> None:
    """Best-effort: promote allowlisted emails to staff in dev/staging."""
    try:
        if not bool(getattr(settings, 'ENABLE_BOOTSTRAP_ADMINS', False)):
            return
        allow = getattr(settings, 'BOOTSTRAP_ADMIN_EMAILS', None)
        if not allow:
            return
        email = (getattr(user, 'email', '') or '').strip().lower()
        if not email or email not in set(allow):
            return
        if not getattr(user, 'is_staff', False):
            user.is_staff = True
            user.save(update_fields=['is_staff'])
    except Exception:
        # Never block auth flows on bootstrap promotion.
        return


def _tenant_id_claim(user: User) -> str | None:
    """Return a safe tenant_id claim value for JWT payloads.

    Important: do NOT stringify None ("None"), because many views filter UUIDFields
    using this value and Django will raise a ValueError (500) for invalid UUIDs.
    """

    tenant_id = getattr(user, 'tenant_id', None)
    return str(tenant_id) if tenant_id else None


class TokenView(APIView):
    """POST /api/auth/login/ - Authenticate user and generate JWT token"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
    @extend_schema(request=LoginRequestSerializer, responses={200: LoginResponseSerializer})
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

        _bootstrap_admin_if_enabled(user)
        
        refresh = RefreshToken.for_user(user)
        # Embed commonly needed claims so downstream requests don't require a DB lookup.
        is_admin = bool(user.is_staff or user.is_superuser)
        is_superadmin = bool(user.is_superuser)
        tenant_id = _tenant_id_claim(user)
        refresh['email'] = user.email
        refresh['tenant_id'] = tenant_id
        refresh['is_admin'] = is_admin
        refresh['is_superadmin'] = is_superadmin
        access = refresh.access_token
        access['email'] = user.email
        access['tenant_id'] = tenant_id
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
                'tenant_id': tenant_id,
                'is_admin': is_admin,
                'is_superadmin': is_superadmin,
            }
        }, status=status.HTTP_200_OK)


class RegisterView(APIView):
    """POST /api/auth/register/ - Register new user"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
    @extend_schema(request=RegisterRequestSerializer, responses={201: RegisterResponseSerializer})
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

        _bootstrap_admin_if_enabled(user)

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
    
    @extend_schema(responses={200: UserContextSerializer})
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
    
    @extend_schema(responses={200: MessageResponseSerializer})
    def post(self, request):
        return Response({'message': 'Logged out'}, status=status.HTTP_200_OK)


class RefreshTokenView(APIView):
    """POST /api/auth/refresh/ - Refresh token"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
    @extend_schema(request=RefreshTokenRequestSerializer, responses={200: RefreshTokenResponseSerializer})
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
    
    @extend_schema(request=RequestOTPRequestSerializer, responses={200: MessageResponseSerializer})
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
    
    @extend_schema(request=VerifyEmailOTPRequestSerializer, responses={200: VerifyEmailOTPResponseSerializer})
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
            tenant_id = _tenant_id_claim(user)
            refresh['email'] = user.email
            refresh['tenant_id'] = tenant_id
            refresh['is_admin'] = is_admin
            refresh['is_superadmin'] = is_superadmin
            access = refresh.access_token
            access['email'] = user.email
            access['tenant_id'] = tenant_id
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
                    'tenant_id': tenant_id,
                    'is_admin': is_admin,
                    'is_superadmin': is_superadmin,
                }
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


class GoogleLoginView(APIView):
    """POST /api/auth/google/ - Login/register with Google ID token (credential)"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def check_throttles(self, request):
        """Fail-open throttling for Google auth.

        Google sign-in should not hard-fail if cache/Redis is temporarily unavailable.
        """
        try:
            return super().check_throttles(request)
        except Exception as exc:
            logger.warning("GoogleLoginView throttle backend unavailable; skipping throttle: %s", exc)
            return

    @extend_schema(request=GoogleLoginRequestSerializer, responses={200: LoginResponseSerializer})
    def post(self, request):
        if google_id_token is None or google_requests is None:
            return Response(
                {'error': 'Google auth not configured on server'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        credential = request.data.get('credential') or request.data.get('id_token')
        if not credential:
            return Response({'error': 'Google credential required'}, status=status.HTTP_400_BAD_REQUEST)

        def _clean(v):
            if v is None:
                return None
            v = str(v).strip()
            return v or None

        # Support multiple env var names for smoother deployments.
        # Backend uses GOOGLE_CLIENT_ID; frontend uses NEXT_PUBLIC_GOOGLE_CLIENT_ID.
        # Some deployments may have legacy/typo keys as well.
        primary_client_id = (
            _clean(getattr(settings, 'GOOGLE_CLIENT_ID', None))
            or _clean(os.getenv('GOOGLE_CLIENT_ID'))
            or _clean(os.getenv('NEXT_PUBLIC_GOOGLE_CLIENT_ID'))
            or _clean(os.getenv('Google_reidirect'))
        )
        extra_client_ids_raw = os.getenv('GOOGLE_CLIENT_IDS', '')
        extra_client_ids = [c.strip() for c in extra_client_ids_raw.split(',') if c.strip()]
        client_ids = [c for c in [primary_client_id, *extra_client_ids] if c]
        if not client_ids:
            return Response(
                {'error': 'GOOGLE_CLIENT_ID not set on server'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            info = None
            last_error = None
            for client_id in client_ids:
                try:
                    info = google_id_token.verify_oauth2_token(
                        credential,
                        google_requests.Request(),
                        client_id,
                        clock_skew_in_seconds=10,
                    )
                    break
                except Exception as e:
                    last_error = e
                    continue

            if not info:
                if last_error:
                    logger.warning('Google token verification failed', exc_info=last_error)
                if getattr(settings, 'DEBUG', False) and last_error:
                    return Response(
                        {
                            'error': f'Invalid Google token: {last_error}',
                            'detail': str(last_error),
                        },
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
                return Response({'error': 'Invalid Google token'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.exception('Unexpected error verifying Google token')
            if getattr(settings, 'DEBUG', False):
                return Response(
                    {
                        'error': f'Invalid Google token: {e}',
                        'detail': str(e),
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return Response({'error': 'Invalid Google token'}, status=status.HTTP_401_UNAUTHORIZED)

        email = (info.get('email') or '').strip().lower()
        email_verified = bool(info.get('email_verified'))
        if not email:
            return Response({'error': 'Google account email not available'}, status=status.HTTP_400_BAD_REQUEST)
        if not email_verified:
            return Response({'error': 'Google email not verified'}, status=status.HTTP_400_BAD_REQUEST)

        given_name = (info.get('given_name') or '').strip()
        family_name = (info.get('family_name') or '').strip()

        user, _created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': given_name,
                'last_name': family_name,
                'tenant_id': _resolve_tenant_id_for_email(email),
                'is_active': True,
            },
        )

        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])

        _bootstrap_admin_if_enabled(user)

        refresh = RefreshToken.for_user(user)
        is_admin = bool(user.is_staff or user.is_superuser)
        is_superadmin = bool(user.is_superuser)
        tenant_id = _tenant_id_claim(user)
        refresh['email'] = user.email
        refresh['tenant_id'] = tenant_id
        refresh['is_admin'] = is_admin
        refresh['is_superadmin'] = is_superadmin
        access = refresh.access_token
        access['email'] = user.email
        access['tenant_id'] = tenant_id
        access['is_admin'] = is_admin
        access['is_superadmin'] = is_superadmin

        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        return Response(
            {
                'access': str(access),
                'refresh': str(refresh),
                'user': {
                    'user_id': str(user.user_id),
                    'email': user.email,
                    'tenant_id': tenant_id,
                    'is_admin': is_admin,
                    'is_superadmin': is_superadmin,
                },
            },
            status=status.HTTP_200_OK,
        )


class ForgotPasswordView(APIView):
    """POST /api/auth/forgot-password/ - Request password reset"""
    permission_classes = [AllowAny]
    throttle_scope = 'auth'
    
    @extend_schema(request=ForgotPasswordRequestSerializer, responses={200: MessageResponseSerializer})
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
    
    @extend_schema(request=VerifyPasswordResetOTPRequestSerializer, responses={200: VerifyPasswordResetOTPResponseSerializer})
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
    
    @extend_schema(request=RequestOTPRequestSerializer, responses={200: MessageResponseSerializer})
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
    
    @extend_schema(request=ResetPasswordRequestSerializer, responses={200: MessageResponseSerializer})
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
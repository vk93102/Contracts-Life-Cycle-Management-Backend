"""
Middleware for tenant isolation and audit logging
"""
import logging
import json
import hashlib
import uuid
import time
from django.db import connection
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.conf import settings

try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    Counter = None
    Histogram = None

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('audit')


class TenantIsolationMiddleware(MiddlewareMixin):
    """
    Middleware to inject tenant_id from JWT token into request
    Ensures all queries are tenant-isolated
    """
    
    def process_request(self, request):
        """
        Extract tenant_id from authenticated user and add to request
        """
        try:
            if hasattr(request, 'user') and request.user.is_authenticated:
                # Add tenant_id to request for use in views/queries
                request.tenant_id = getattr(request.user, 'tenant_id', None)
                
                if not request.tenant_id:
                    logger.warning(f"User {request.user.id} has no tenant_id")
                else:
                    logger.debug(f"Tenant {request.tenant_id} injected for user {request.user.id}")
            
            return None
        except Exception as e:
            logger.error(f"Error in TenantIsolationMiddleware: {str(e)}")
            return None


class RequestIdMiddleware(MiddlewareMixin):
    """Attach a request id for correlation across logs/traces."""

    HEADER = 'X-Request-ID'

    def process_request(self, request):
        rid = request.META.get('HTTP_X_REQUEST_ID')
        if not rid:
            rid = str(uuid.uuid4())
        request.request_id = rid
        return None

    def process_response(self, request, response):
        rid = getattr(request, 'request_id', None)
        if rid:
            response.headers.setdefault(self.HEADER, rid)
        return response


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all API requests for audit trail
    """
    
    # Endpoints to exclude from logging (noisy/frequent)
    EXCLUDED_PATHS = [
        '/api/health/',
        '/static/',
        '/media/',
    ]
    
    def should_log(self, path):
        """Check if this path should be logged"""
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return False
        return True
    
    def get_request_hash(self, request):
        """Create hash of request for integrity checking"""
        try:
            data = {
                'method': request.method,
                'path': request.path,
                'timestamp': timezone.now().isoformat(),
            }
            
            # Add body for POST/PUT requests
            if request.method in ['POST', 'PUT', 'PATCH']:
                try:
                    body = request.body.decode('utf-8') if request.body else ''
                    if len(body) < 1000:  # Only hash if small enough
                        data['body'] = body
                except:
                    pass
            
            json_str = json.dumps(data, sort_keys=True)
            return hashlib.sha256(json_str.encode()).hexdigest()
        except Exception as e:
            logger.warning(f"Could not generate request hash: {e}")
            return None
    
    def process_request(self, request):
        """Store request info for later logging"""
        if self.should_log(request.path):
            # Store info on request object for access in process_response
            request._audit_log_data = {
                'method': request.method,
                'path': request.path,
                'remote_addr': self.get_client_ip(request),
                'user_id': getattr(request.user, 'id', None) if hasattr(request, 'user') and request.user.is_authenticated else None,
                'tenant_id': getattr(request.user, 'tenant_id', None) if hasattr(request, 'user') and request.user.is_authenticated else None,
                'request_hash': self.get_request_hash(request),
                'timestamp': timezone.now(),
                'request_id': getattr(request, 'request_id', None),
            }
        
        return None
    
    def process_response(self, request, response):
        """Log the API response"""
        if hasattr(request, '_audit_log_data'):
            try:
                audit_data = request._audit_log_data
                
                # Only log API endpoints
                if audit_data['path'].startswith('/api/'):
                    # Log to audit logger
                    audit_logger.info(
                        f"API_CALL|method={audit_data['method']}|endpoint={audit_data['path']}|"
                        f"status={response.status_code}|user_id={audit_data['user_id']}|"
                        f"tenant_id={audit_data['tenant_id']}|ip={audit_data['remote_addr']}|"
                        f"request_id={audit_data.get('request_id')}|hash={audit_data['request_hash']}"
                    )
                    
                    # Log errors to warning
                    if response.status_code >= 400:
                        logger.warning(
                            f"API Error: {audit_data['method']} {audit_data['path']} - "
                            f"Status: {response.status_code} - User: {audit_data['user_id']}"
                        )
            except Exception as e:
                logger.error(f"Failed to log API call: {str(e)}")
        
        return response
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class PIIProtectionLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log PII redaction operations
    """
    
    def process_request(self, request):
        """Log PII operations"""
        try:
            if request.path.startswith('/api/') and 'redaction' in request.path.lower():
                user_id = getattr(request.user, 'id', None) if hasattr(request, 'user') and request.user.is_authenticated else 'unknown'
                logger.info(
                    f"PII Redaction operation by user {user_id}: "
                    f"{request.method} {request.path}"
                )
        except Exception as e:
            logger.warning(f"Error in PIIProtectionLoggingMiddleware: {e}")
        
        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Add security headers for API responses.

    Django's SecurityMiddleware covers some headers; this middleware ensures
    consistent headers for API responses and enables CSP configuration.
    """

    def process_response(self, request, response):
        try:
            # Basic hardening
            response.headers.setdefault('X-Content-Type-Options', 'nosniff')
            response.headers.setdefault('Referrer-Policy', getattr(settings, 'SECURE_REFERRER_POLICY', 'same-origin'))

            # If you must allow framing (e.g. embedded signing), configure via env.
            xfo = getattr(settings, 'X_FRAME_OPTIONS', None)
            if xfo:
                response.headers.setdefault('X-Frame-Options', xfo)

            # CSP is off by default; enable only once frontend requirements are known.
            csp = getattr(settings, 'CONTENT_SECURITY_POLICY', None)
            if csp:
                response.headers.setdefault('Content-Security-Policy', csp)

            # Force no-store on auth endpoints
            if request.path.startswith('/api/auth/'):
                response.headers.setdefault('Cache-Control', 'no-store')
                response.headers.setdefault('Pragma', 'no-cache')
        except Exception:
            # Never break response pipeline for headers.
            pass
        return response


if Counter is not None and Histogram is not None:
    API_REQUEST_COUNT = Counter(
        'clm_api_requests_total',
        'Total API requests',
        ['method', 'path', 'status'],
    )
    API_REQUEST_LATENCY = Histogram(
        'clm_api_request_latency_seconds',
        'API request latency (seconds)',
        ['method', 'path'],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    )
else:
    API_REQUEST_COUNT = None
    API_REQUEST_LATENCY = None


class MetricsMiddleware(MiddlewareMixin):
    """Prometheus request metrics for /api/* routes."""

    def process_request(self, request):
        request._metrics_start_ts = timezone.now()
        return None

    def process_response(self, request, response):
        if not getattr(request, 'path', '').startswith('/api/'):
            return response

        if API_REQUEST_COUNT is None or API_REQUEST_LATENCY is None:
            return response

        try:
            start = getattr(request, '_metrics_start_ts', None)
            if start is None:
                return response
            duration = (timezone.now() - start).total_seconds()

            method = getattr(request, 'method', 'GET')
            # Reduce cardinality: strip ids/uuids by coarse routing.
            path = getattr(request, 'path', '')
            if len(path) > 120:
                path = path[:120]

            status_code = getattr(response, 'status_code', 200)

            API_REQUEST_COUNT.labels(method=method, path=path, status=str(status_code)).inc()
            API_REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
        except Exception:
            pass

        return response


class SlowQueryLoggingMiddleware(MiddlewareMixin):
    """Log slow DB queries per-request.

    Enable by setting `DB_SLOW_QUERY_MS` (e.g. 200).
    This uses Django's `connection.execute_wrapper` to time individual queries
    during request handling and logs any query above the threshold.
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        try:
            self.threshold_ms = int(getattr(settings, 'DB_SLOW_QUERY_MS', 0) or 0)
        except Exception:
            self.threshold_ms = 0
        self._logger = logging.getLogger('clm_backend.slowdb')

    def __call__(self, request):
        if not self.threshold_ms:
            return self.get_response(request)

        threshold_ms = self.threshold_ms

        def _wrapper(execute, sql, params, many, context):
            started = time.monotonic()
            try:
                return execute(sql, params, many, context)
            finally:
                elapsed_ms = (time.monotonic() - started) * 1000.0
                if elapsed_ms < threshold_ms:
                    return

                # Avoid flooding logs with huge payloads.
                sql_s = (sql or '').strip().replace('\n', ' ')
                if len(sql_s) > 2000:
                    sql_s = sql_s[:2000] + '…'

                params_s = None
                try:
                    params_s = repr(params)
                    if len(params_s) > 1000:
                        params_s = params_s[:1000] + '…'
                except Exception:
                    params_s = '<unrepr>'

                self._logger.warning(
                    'SLOW_DB_QUERY ms=%.1f method=%s path=%s request_id=%s sql=%s params=%s',
                    elapsed_ms,
                    getattr(request, 'method', ''),
                    getattr(request, 'path', ''),
                    getattr(request, 'request_id', None),
                    sql_s,
                    params_s,
                )

        with connection.execute_wrapper(_wrapper):
            return self.get_response(request)

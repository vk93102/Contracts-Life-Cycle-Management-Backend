from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class TenantUserRateThrottle(SimpleRateThrottle):
    """Rate limit authenticated callers per (tenant_id, user_id).

    Falls back to IP-based identity when unauthenticated or missing claims.

    Configure rate via REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['tenant_user'].
    """

    scope = "tenant_user"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)

        if user is not None and getattr(user, "is_authenticated", False):
            tenant_id = getattr(request, "tenant_id", None) or getattr(user, "tenant_id", None)
            user_id = (
                getattr(user, "user_id", None)
                or getattr(user, "id", None)
                or getattr(user, "pk", None)
            )

            if tenant_id and user_id:
                ident = f"{tenant_id}:{user_id}"
            elif user_id:
                ident = str(user_id)
            else:
                ident = self.get_ident(request)
        else:
            ident = self.get_ident(request)

        return self.cache_format % {"scope": self.scope, "ident": ident}

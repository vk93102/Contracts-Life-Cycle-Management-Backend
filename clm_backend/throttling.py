from __future__ import annotations

import logging

from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.throttling import SimpleRateThrottle


logger = logging.getLogger(__name__)


class FailOpenThrottleMixin:
    """Fail-open throttling: never crash request handling due to cache outages.

    If Redis/Django cache is unreachable, we allow the request and log a warning.
    This keeps auth and critical APIs available in degraded local/dev environments.
    """

    def allow_request(self, request, view):  # type: ignore[override]
        try:
            return super().allow_request(request, view)
        except Exception as exc:  # pragma: no cover - depends on runtime cache/network
            logger.warning(
                "Throttle cache unavailable; allowing request (scope=%s, path=%s): %s",
                getattr(self, "scope", "unknown"),
                getattr(request, "path", ""),
                exc,
            )
            return True


class SafeAnonRateThrottle(FailOpenThrottleMixin, AnonRateThrottle):
    pass


class SafeScopedRateThrottle(FailOpenThrottleMixin, ScopedRateThrottle):
    pass


class TenantUserRateThrottle(FailOpenThrottleMixin, SimpleRateThrottle):
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

from __future__ import annotations

import os
from typing import Optional

from django.http import HttpRequest, HttpResponse


def _is_authorized(request: HttpRequest) -> bool:
    token = (os.getenv('METRICS_TOKEN') or '').strip()
    if not token:
        return True

    header = (request.headers.get('X-Metrics-Token') or '').strip()
    return header == token


def metrics_view(request: HttpRequest) -> HttpResponse:
    """Prometheus scrape endpoint.

    Set `METRICS_TOKEN` to require `X-Metrics-Token` header.
    """

    if not _is_authorized(request):
        return HttpResponse('unauthorized', status=401, content_type='text/plain; version=0.0.4')

    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except Exception:
        return HttpResponse('prometheus_client not installed', status=501, content_type='text/plain')

    payload = generate_latest()
    return HttpResponse(payload, content_type=CONTENT_TYPE_LATEST)

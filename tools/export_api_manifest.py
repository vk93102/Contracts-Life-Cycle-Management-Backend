#!/usr/bin/env python3
"""Export all Django/DRF URL patterns into a manifest for api_test_runner.

This is the reliable way to get "100+ endpoints" without missing router-generated URLs.

Usage:
  python3 CLM_Backend/tools/export_api_manifest.py \
    --out ops/performance/api_test_manifest_full.json

Optional:
  --include-admin           include /admin/ endpoints
  --include-non-api         include non-/api* endpoints (besides /metrics)

Auth settings are written as placeholders; update in the generated manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import django
from django.urls import URLPattern, URLResolver, get_resolver


HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _setup() -> None:
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "clm_backend.settings")
    django.setup()


def _iter_patterns(patterns: Iterable[Any], prefix: str = "") -> Iterable[Tuple[str, URLPattern]]:
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _iter_patterns(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield (prefix + str(p.pattern), p)


def _normalize_path(route: str) -> str:
    path = route or ""

    # If a regex-style pattern leaks through (e.g. "^contracts/(?P<pk>[^/.]+)/$")
    # convert it into a readable path template.
    if "(?P<" in path or "^" in path or "$" in path:
        # Anchors can appear in the middle when prefixes are concatenated.
        path = path.replace("^", "")
        path = path.replace("$", "")
        path = path.replace("\\Z", "")
        # Convert named groups to <name>
        path = re.sub(r"\(\?P<([A-Za-z_][A-Za-z0-9_]*)>[^\)]*\)", r"<\1>", path)
        # Drop regex escapes
        path = path.replace("\\.", ".")
        path = path.replace("\\/", "/")
        path = path.replace("\\-", "-")
        # Convert optional trailing slash patterns
        path = path.replace("/?", "/")

    if not path.startswith("/"):
        path = "/" + path
    # Remove duplicated slashes
    while "//" in path:
        path = path.replace("//", "/")
    return path


def _callback_methods(pattern: URLPattern) -> List[str]:
    cb = pattern.callback

    # DRF ViewSet routes (router) expose .actions on the callback
    actions = getattr(cb, "actions", None)
    if isinstance(actions, dict) and actions:
        return sorted({m.upper() for m in actions.keys() if m and m.lower() in {x.lower() for x in HTTP_METHODS}})

    # Class-based views created via as_view expose .cls
    cls = getattr(cb, "cls", None)
    if cls is not None:
        # Prefer implemented methods
        methods: List[str] = []
        for m in HTTP_METHODS:
            mm = m.lower()
            if hasattr(cls, mm):
                methods.append(m)
        # If nothing found, fall back to http_method_names
        if not methods:
            http_method_names = getattr(cls, "http_method_names", []) or []
            methods = [m.upper() for m in http_method_names if m and m.upper() in HTTP_METHODS]
        return sorted(set(methods)) or ["GET"]

    # Function-based view: assume GET
    return ["GET"]


def _nice_name(pattern: URLPattern) -> str:
    if pattern.name:
        return str(pattern.name)

    cb = pattern.callback
    cls = getattr(cb, "cls", None)
    if cls is not None:
        return cls.__name__

    try:
        return cb.__name__
    except Exception:
        return "endpoint"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output manifest JSON path")
    ap.add_argument("--include-admin", action="store_true")
    ap.add_argument("--include-non-api", action="store_true")
    args = ap.parse_args()

    _setup()
    resolver = get_resolver()

    endpoints: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    for route, pattern in _iter_patterns(resolver.url_patterns, prefix=""):
        # Drop DRF-style optional format suffix routes (e.g. \\.(?P<format>...))
        # These are not practical to call from a simple HTTP runner.
        if "(?P<format>" in route or "<format>" in route:
            continue
        path = _normalize_path(route)

        if "<format>" in path:
            continue

        # Filtering
        if not args.include_admin and path.startswith("/admin/"):
            continue
        if not args.include_non_api:
            if not (path.startswith("/api/") or path.startswith("/api/v1/") or path == "/metrics"):
                continue

        methods = _callback_methods(pattern)
        name = _nice_name(pattern)

        for method in methods:
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)

            endpoints.append(
                {
                    "name": name,
                    "method": method,
                    "path": path,
                    "auth": True,
                    "expected_status": [200, 201, 202, 204, 400, 401, 403, 404, 405],
                    "notes": "auto-exported",
                }
            )

    endpoints.sort(key=lambda e: (e["path"], e["method"]))

    manifest: Dict[str, Any] = {
        "auth": {"email": "admin@example.com", "password": "admin12345"},
        "endpoints": endpoints,
        "flows": {
            "all_smoke": [
                {"name": "Health", "method": "GET", "path": "/api/v1/health/", "auth": False, "expected_status": [200]},
                {"name": "Auth: Me", "method": "GET", "path": "/api/auth/me/", "auth": True, "expected_status": [200, 401]},
                {"name": "Templates: Types", "method": "GET", "path": "/api/v1/templates/types/", "auth": True, "expected_status": [200, 401, 403]},
                {"name": "Contracts: List", "method": "GET", "path": "/api/v1/contracts/", "auth": True, "expected_status": [200, 401, 403]},
                {"name": "Workflows: List", "method": "GET", "path": "/api/v1/workflows/", "auth": True, "expected_status": [200, 401, 403]}
            ]
        }
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Exported endpoints: {len(endpoints)}")
    print(f"Wrote manifest: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

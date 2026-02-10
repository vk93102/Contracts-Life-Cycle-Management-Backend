#!/usr/bin/env python3
"""Ensure a DB-backed test user exists for local perf/E2E runs.

This is intentionally tiny and deterministic so automated test runs can rely on
known credentials in `ops/performance/api_test_manifest*.json`.

Usage:
  python3 CLM_Backend/tools/ensure_test_user.py --email admin@example.com --password admin12345 --admin
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--admin", action="store_true", help="Make user staff/superuser")
    ap.add_argument("--tenant-domain", default="", help="Optional tenant domain to look up/create")
    args = ap.parse_args()

    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "clm_backend.settings")
    import django

    django.setup()

    from authentication.models import User
    from tenants.models import TenantModel

    email = args.email.strip().lower()
    password = args.password

    tenant = None
    if args.tenant_domain.strip():
        tenant = TenantModel.objects.filter(domain=args.tenant_domain.strip().lower()).first()

    if tenant is None:
        tenant = TenantModel.objects.filter(status="active").order_by("created_at").first()

    if tenant is None:
        domain = (email.split("@", 1)[1] if "@" in email else "tenant.local").strip().lower() or "tenant.local"
        tenant = TenantModel.objects.create(
            name=f"Tenant {domain}",
            domain=domain,
            status="active",
            subscription_plan="free",
        )

    user = User.objects.filter(email=email).first()
    created = False
    if user is None:
        user = User(email=email, is_active=True, tenant_id=tenant.id)
        created = True

    user.is_active = True
    user.tenant_id = tenant.id
    if args.admin:
        user.is_staff = True
        user.is_superuser = True

    user.set_password(password)
    user.save()

    print(
        {
            "created": created,
            "email": user.email,
            "user_id": str(user.user_id),
            "tenant_id": str(user.tenant_id),
            "is_staff": bool(user.is_staff),
            "is_superuser": bool(user.is_superuser),
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

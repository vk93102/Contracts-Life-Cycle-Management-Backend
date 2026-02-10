#!/usr/bin/env python
"""E2E proof: signup -> OTP verify -> login -> /me

This script is meant for LOCAL validation and evidence.
It performs real HTTP requests against the running backend and reads the OTP
from the database via Postgres (so you don't need to access email inboxes).

Usage:
  python tools/e2e_auth_signup_otp_flow.py

Env:
    CLM_API_BASE_URL (default: http://127.0.0.1:11000)
"""

from __future__ import annotations

import os
import time
from urllib.parse import urlparse, unquote

import requests
from dotenv import load_dotenv


def _load_env() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    backend_root = os.path.abspath(os.path.join(here, ".."))
    load_dotenv(os.path.join(backend_root, ".env"), override=False)


def _pg_conn_kwargs() -> dict:
    database_url = (os.environ.get("DATABASE_URL") or "").strip()
    if database_url:
        parsed = urlparse(database_url)
        if (parsed.scheme or "").lower() not in ("postgres", "postgresql"):
            raise RuntimeError("DATABASE_URL must start with postgresql://")
        return {
            "dbname": (parsed.path or "").lstrip("/") or "postgres",
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "host": parsed.hostname or "",
            "port": parsed.port or 5432,
            "sslmode": (dict([kv.split("=") for kv in (parsed.query or "").split("&") if "=" in kv]).get("sslmode")
                        if parsed.query else None) or os.environ.get("DB_SSLMODE", "require"),
        }

    return {
        "dbname": os.environ.get("DB_NAME", "postgres"),
        "user": os.environ.get("DB_USER", ""),
        "password": os.environ.get("DB_PASSWORD", ""),
        "host": os.environ.get("DB_HOST", ""),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "sslmode": os.environ.get("DB_SSLMODE", "require"),
    }


def _fetch_login_otp_from_db(email: str) -> str:
    import psycopg2  # noqa: WPS433

    kw = _pg_conn_kwargs()
    missing = [k for k in ("user", "password", "host") if not str(kw.get(k) or "").strip()]
    if missing:
        raise RuntimeError(f"Missing DB connection env vars: {', '.join(missing)}")

    with psycopg2.connect(**kw) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT login_otp FROM clm_users WHERE email=%s", (email.lower(),))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("User not found in DB")
            return (row[0] or "").strip()


def main() -> int:
    base_url = os.environ.get("CLM_API_BASE_URL", "http://127.0.0.1:11000").rstrip("/")

    _load_env()

    ts = int(time.time())
    email = f"e2e_{ts}@example.com"
    password = "TestPass123!"

    print(f"Base URL: {base_url}")
    print(f"Email:    {email}")

    # 1) Register (pending verification)
    r = requests.post(
        f"{base_url}/api/auth/register/",
        json={
            "email": email,
            "password": password,
            "full_name": "E2E Test",
            "company": "E2E Inc",
        },
        timeout=20,
    )
    print(f"REGISTER status={r.status_code} body={r.text[:300]}")
    if r.status_code not in (200, 201):
        return 1

    # 2) Read OTP from DB
    try:
        otp = _fetch_login_otp_from_db(email)
    except Exception as e:
        print(f"ERROR: failed to fetch OTP from DB: {e}")
        return 2
    if not otp:
        print("ERROR: OTP not found on user record (login_otp is empty)")
        return 2

    print(f"OTP:      {otp}")

    # 3) Verify OTP (should activate + return tokens)
    v = requests.post(
        f"{base_url}/api/auth/verify-email-otp/",
        json={"email": email, "otp": otp},
        timeout=20,
    )
    print(f"VERIFY status={v.status_code} body={v.text[:300]}")
    if v.status_code != 200:
        return 3

    data = v.json()
    access = data.get("access")
    if not access:
        print("ERROR: No access token returned from verify-email-otp")
        return 4

    # 4) Call /me with access token
    me = requests.get(
        f"{base_url}/api/auth/me/",
        headers={"Authorization": f"Bearer {access}"},
        timeout=20,
    )
    print(f"ME status={me.status_code} body={me.text[:300]}")
    if me.status_code != 200:
        return 5

    me_data = me.json()
    if (me_data.get("email") or "").lower() != email.lower():
        print("ERROR: /me returned unexpected email")
        return 6

    # 5) Login with password (should succeed now)
    l = requests.post(
        f"{base_url}/api/auth/login/",
        json={"email": email, "password": password},
        timeout=20,
    )
    print(f"LOGIN status={l.status_code} body={l.text[:300]}")
    if l.status_code != 200:
        return 7

    print("\n✅ E2E AUTH FLOW OK: register -> OTP verify -> /me -> login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

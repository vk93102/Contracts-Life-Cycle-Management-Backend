# CLM Backend (Django + DRF)

Contract Lifecycle Management backend built on **Django 5** and **Django REST Framework**, with JWT auth, AI-assisted features, background jobs (Celery), and observability hooks.

## What’s inside

- **Framework**: Django, DRF
- **Auth**: JWT (SimpleJWT) + custom stateless auth class
- **API docs**: OpenAPI schema + Swagger UI
- **Async jobs**: Celery (Redis broker/result backend)
- **Storage**: Cloudflare R2 (S3-compatible) for uploads
- **AI**: Gemini + VoyageAI integrations (keys via env)
- **DB**: PostgreSQL via Supabase (direct host or pooler)

## Requirements

- Python **3.11.x** (see `runtime.txt`)
- A Supabase Postgres database (or set `SUPABASE_ONLY=False` for local Postgres)
- Optional for background jobs: Redis

## Quick start (local)

From the repo root:

```bash
cd CLM_Backend

# Create/activate venv (example)
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 1) Configure environment

This project loads environment variables from:

1) `CLM_Backend/.env` (preferred)
2) `CLM_Backend/contracts/.env` (fallback; only fills missing vars)

Create `CLM_Backend/.env` with at least:

```dotenv
# Django
DEBUG=True
DJANGO_SECRET_KEY=change-me

# Database (Supabase)
SUPABASE_ONLY=True
DB_HOST=db.<project-ref>.supabase.co
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=... # never commit
DB_SSLMODE=require

# Optional: prefer transaction pooler to avoid max clients issues
# DB_HOST=aws-0-...pooler.supabase.com
# DB_POOLER_MODE=transaction
# DB_PORT=6543

# CORS
CORS_ALLOWED_ORIGINS_EXTRA=http://localhost:3000

# AI (optional depending on feature usage)
GEMINI_API_KEY=
VOYAGE_API_KEY=

# Email (optional unless SECURITY_STRICT=True)
GMAIL=
APP_PASSWORD=

# Redis / Celery (optional for background jobs)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Cloudflare R2 (optional unless file features are used)
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_ENDPOINT_URL=
R2_PUBLIC_URL=
```

Notes:

- **Supabase-only safety**: by default `SUPABASE_ONLY=True` will refuse non-Supabase DB hosts.
- If you need to run against local Postgres for development, set `SUPABASE_ONLY=False`.

### 2) Migrate + run

```bash
python manage.py migrate

# Use 11000 if you plan to use the included tooling/scripts
python manage.py runserver 0.0.0.0:11000
```

## Important endpoints

- Swagger UI: `GET /api/docs/`
- OpenAPI schema: `GET /api/schema/`
- Metrics: `GET /metrics`
- Admin: `GET /admin/`

Top-level routing is defined in `clm_backend/urls.py`.

## Background jobs (Celery)

If you use features that enqueue tasks, start Redis and a Celery worker.

```bash
# Terminal A (Redis)
redis-server

# Terminal B (Celery worker)
cd CLM_Backend
source .venv/bin/activate
celery -A clm_backend worker -l info
```

## Testing

- App/unit tests live alongside apps (e.g. `authentication/tests.py`, `audit_logs/test_audit_logging.py`).
- A production-style API validation suite exists under `tests/`.

Examples:

```bash
# Django test runner
python manage.py test

# Production suite runner (see tests/README_PRODUCTION_TESTS.md)
bash tests/run_production_tests.sh
```

## Troubleshooting

### “SUPABASE_ONLY is enabled but DB host is not a Supabase host”

- Set `DB_HOST` to your Supabase host (e.g. `db.<ref>.supabase.co`) or pooler host (`...pooler.supabase.com`).
- Or set `SUPABASE_ONLY=False` for local Postgres.

### Supabase pooler “max clients reached”

- Prefer transaction mode (`DB_POOLER_MODE=transaction`, commonly port `6543`).
- Keep Django connections short (`DB_CONN_MAX_AGE=0` is the default for poolers).

## Repo navigation

- `clm_backend/`: project settings, urls, middleware, schema
- App modules: `authentication/`, `contracts/`, `ai/`, `search/`, `workflows/`, etc.
- `docs/`: backend documentation
- `tools/`: small CLI/e2e helpers
- `tests/`: integration/prod-style test suite

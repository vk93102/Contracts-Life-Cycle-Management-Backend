# 📋 CLM Backend (Django + DRF)

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-green?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.14-red?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-blue?logo=postgresql&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-green?logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-5.0-red?logo=redis&logoColor=white)

**Enterprise-grade Contract Lifecycle Management backend** built with Django, DRF, AI integrations, and real-time processing capabilities.

</div>

---

## 🎯 Overview

A production-ready Django REST Framework backend for contract management featuring:
- 🔐 **JWT-based authentication** with stateless token validation
- 🤖 **AI-powered features** (Gemini + VoyageAI for NLP/embeddings)
- ⚡ **Async task processing** with Celery
- 📊 **OpenTelemetry observability** + Prometheus metrics
- 🔍 **Advanced search** (semantic + full-text)
- 📝 **Multi-tenant architecture** with row-level isolation
- ☁️ **Cloud storage** (Cloudflare R2)
- 📄 **Auto-generated API docs** (Swagger/OpenAPI)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLM Backend                              │
│                     (Django + DRF API)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌────────────────────────────────────────────┐
        │         Core Components                     │
        ├────────────────────────────────────────────┤
        │  • Authentication (JWT + OTP)              │
        │  • Contracts Management                    │
        │  • AI Features (NLP/Extraction)            │
        │  • Search (Semantic + Full-text)           │
        │  • Workflows & Approvals                   │
        │  • Calendar & Reviews                      │
        │  • Audit Logging                           │
        │  • Multi-tenant Isolation                  │
        └────────────────────────────────────────────┘
                              │
        ┌─────────────────────┴───────────────────────┐
        ▼                     ▼                     ▼
  ┌──────────┐       ┌──────────────┐      ┌──────────────┐
  │PostgreSQL│       │    Celery    │      │ Cloudflare   │
  │(Supabase)│       │   Workers    │      │      R2      │
  │          │       │              │      │   Storage    │
  │• pgvector│       │• Task Queue  │      │              │
  │• pg_trgm │       │• Redis Broker│      │• PDF/Docs    │
  └──────────┘       └──────────────┘      └──────────────┘
        │                     │
        ▼                     ▼
  ┌──────────┐       ┌──────────────┐
  │   AI     │       │    Redis     │
  │Services  │       │   Cache      │
  │          │       │              │
  │• Gemini  │       │• DRF Throttle│
  │• VoyageAI│       │• Sessions    │
  └──────────┘       └──────────────┘
```

---

## ✨ Key Features

### 🔐 Authentication & Security
- JWT-based stateless authentication
- OTP verification (email)
- Google OAuth integration
- Multi-tenant isolation middleware
- Role-based permissions
- PII protection logging

### 📄 Contract Management
- Full CRUD operations
- Template management
- Clause library
- PDF generation & processing
- Document version control
- OCR & redaction support

### 🤖 AI-Powered Features
- **Metadata extraction** (parties, dates, values)
- **Clause classification** (payment, liability, etc.)
- **Obligation extraction** from contracts
- **Semantic search** with pgvector + VoyageAI
- **Document summarization** (Gemini)
- **Risk analysis** & compliance checks

### 🔍 Search & Discovery
- Semantic search (vector embeddings)
- Full-text search (PostgreSQL)
- Faceted filtering
- Similar clause detection

### 🔄 Workflows & Approvals
- Custom approval workflows
- Multi-stage routing
- Email notifications
- Calendar integration
- Review & signing requests

### 📊 Observability
- Prometheus metrics endpoint
- OpenTelemetry instrumentation
- Request ID tracking
- Slow query logging
- Comprehensive audit logs

---

## 🛠️ Tech Stack

| Category | Technology |
|----------|------------|
| **Framework** | Django 5.0, Django REST Framework 3.14 |
| **Database** | PostgreSQL (Supabase) with pgvector |
| **Cache** | Redis 5.0 |
| **Task Queue** | Celery 5.3 |
| **AI/ML** | Google Gemini, VoyageAI |
| **Storage** | Cloudflare R2 (S3-compatible) |
| **Auth** | SimpleJWT, Google OAuth |
| **API Docs** | drf-spectacular (OpenAPI 3) |
| **Observability** | OpenTelemetry, Prometheus |

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

---

## 📁 Repository Structure

```
CLM_Backend/
├── 📂 clm_backend/          # Core Django project
│   ├── settings.py          # Configuration (DB, auth, CORS, AI)
│   ├── urls.py              # Main URL routing
│   ├── middleware.py        # Custom middleware (tenant, metrics, audit)
│   ├── celery.py            # Celery config
│   └── schema.py            # OpenAPI customization
│
├── 📂 authentication/       # User auth, JWT, OTP, OAuth
│   ├── models.py            # User model
│   ├── views.py             # Login, register, verify
│   ├── jwt_auth.py          # Stateless JWT authentication
│   └── middleware.py        # Auth-related middleware
│
├── 📂 contracts/            # Contract CRUD & templates
│   ├── models.py            # Contract, Clause, Template
│   ├── views.py             # API endpoints
│   ├── pdf_service.py       # PDF generation
│   └── clause_seed.py       # Initial clause data
│
├── 📂 ai/                   # AI-powered features
│   ├── views.py             # Metadata extraction, classification
│   ├── advanced_features.py # Summarization, obligation extraction
│   └── models.py            # AI result caching
│
├── 📂 search/               # Semantic & full-text search
│   ├── views.py             # Search endpoints
│   └── models.py            # Search indexes
│
├── 📂 workflows/            # Approval workflows
├── 📂 approvals/            # Workflow engine
├── 📂 calendar_events/      # Calendar integration
├── 📂 reviews/              # Document review
├── 📂 notifications/        # Email notifications
├── 📂 audit_logs/           # Comprehensive audit trail
├── 📂 tenants/              # Multi-tenant support
├── 📂 repository/           # File upload/storage
├── 📂 ocr/                  # OCR processing
├── 📂 redaction/            # Document redaction
│
├── 📂 docs/                 # Backend documentation
│   └── admin.md             # Admin features
│
├── 📂 tools/                # CLI utilities
│   ├── api_test_runner.py   # API testing tool
│   └── e2e_auth_signup_otp_flow.py
│
├── 📂 tests/                # Test suites
│   ├── README_PRODUCTION_TESTS.md
│   └── run_production_tests.sh
│
├── requirements.txt         # Python dependencies
├── runtime.txt              # Python 3.11.7
└── manage.py                # Django CLI
```

---

## 🔗 API Endpoints Overview

### 🔐 Authentication
```
POST   /api/auth/register/           # Register new user
POST   /api/auth/login/              # Login (get JWT)
POST   /api/auth/verify-otp/         # Verify OTP
POST   /api/auth/google/             # Google OAuth
GET    /api/auth/me/                 # Get current user
POST   /api/auth/refresh/            # Refresh JWT
```

### 📄 Contracts
```
GET    /api/v1/contracts/            # List contracts
POST   /api/v1/contracts/            # Create contract
GET    /api/v1/contracts/{id}/       # Get contract
PATCH  /api/v1/contracts/{id}/       # Update contract
DELETE /api/v1/contracts/{id}/       # Delete contract
```

### 🤖 AI Features
```
POST   /api/v1/ai/extract/metadata/       # Extract metadata
POST   /api/v1/ai/classify/               # Classify clause
POST   /api/v1/ai/extract/obligations/    # Extract obligations
POST   /api/v1/ai/summarize/              # Summarize document
```

### 🔍 Search
```
GET    /api/search/semantic/         # Semantic search
GET    /api/search/full-text/        # Full-text search
```

### 📊 Admin & Monitoring
```
GET    /api/docs/                    # Swagger UI
GET    /api/schema/                  # OpenAPI schema
GET    /metrics                      # Prometheus metrics
GET    /admin/                       # Django admin
```

---

## 🚀 Production Deployment

### Environment Variables (Production)

```bash
# Security
DEBUG=False
SECURITY_STRICT=True
DJANGO_SECRET_KEY=<strong-random-key>
ALLOWED_HOSTS=yourdomain.com,api.yourdomain.com

# Database (Supabase Transaction Pooler recommended)
DB_HOST=aws-0-...pooler.supabase.com
DB_PORT=6543
DB_POOLER_MODE=transaction
DB_CONN_MAX_AGE=0

# SSL & Security Headers
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000

# CORS
CORS_ALLOWED_ORIGINS_EXTRA=https://yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com

# Required Services
REDIS_URL=redis://...
CELERY_BROKER_URL=redis://...
GEMINI_API_KEY=...
VOYAGE_API_KEY=...
R2_ACCESS_KEY_ID=...
```

### Performance Tuning

- Use **Supabase transaction pooler** (port 6543) to avoid connection limits
- Set `DB_CONN_MAX_AGE=0` for pooled connections
- Enable Redis caching for DRF throttling
- Run Celery workers for background tasks
- Monitor with Prometheus + OpenTelemetry

---

## 📚 Additional Documentation

- **Backend API Documentation**: `docs/BACKEND_API_DOCUMENTATION.md`
- **Admin Features**: `docs/admin.md`
- **Production Tests**: `tests/README_PRODUCTION_TESTS.md`
- **Feature Index**: `docs/FEATURES_INDEX.md`

---

## 🤝 Contributing

1. Follow Django/DRF best practices
2. Add tests for new features
3. Update OpenAPI schema annotations
4. Document environment variables
5. Run `python manage.py test` before committing

---

## 📄 License

Proprietary - Contract Lifecycle Management System

---

<div align="center">

**Built with ❤️ using Django & Django REST Framework**

[Backend API Docs](docs/) • [Frontend Repo](../CLM_Frontend/) • [Production Tests](tests/README_PRODUCTION_TESTS.md)

</div>

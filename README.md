# 📋 CLM Backend (Django + DRF)

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-green?logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.14-red?logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-blue?logo=postgresql&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-green?logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-5.0-red?logo=redis&logoColor=white)

**Enterprise-grade Contract Lifecycle Management backend** built with Django, DRF, AI integrations, and real-time processing capabilities.

---

### 🎬 [Watch Demo Video](https://www.loom.com/share/694dee3f381545b2a17f2dc1831c5bd0)

### 📦 Repository Links

| Repo | Link | Status |
|------|------|--------|
| **Backend (You are here)** | [Contracts-Life-Cycle-Management-Backend](https://github.com/vk93102/Contracts-Life-Cycle-Management-Backend) | ✅ |
| **Frontend** | [Contracts-Life-Cycle-Management-Frontend](https://github.com/vk93102/Contracts-Life-Cycle-Management-Frontend) | ✅ |

</div>

---

## 🎯 Overview

A production-ready Django REST Framework backend for contract management featuring:
- 🔐 **JWT-based authentication** with stateless token validation
- 🎯 **Role-based access control** (admin, approver, editor, viewer)
- 📋 **Contract version control** with immutable snapshots
- 🤖 **AI-powered features** (Gemini + VoyageAI for NLP/embeddings)
- ⚡ **Async task processing** with Celery
- 📊 **OpenTelemetry observability** + Prometheus metrics
- 🔍 **Advanced search** (semantic + full-text)
- 📝 **Multi-tenant architecture** with row-level isolation
- ☁️ **Cloud storage** (Cloudflare R2)
- 📄 **Auto-generated API docs** (Swagger/OpenAPI)
- 📢 **Notifications** (email, in-app, webhooks)
- 📋 **Audit logging** with immutable trail

Companion frontend: [Contracts-Life-Cycle-Management-Frontend](https://github.com/vk93102/Contracts-Life-Cycle-Management-Frontend)

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

## 🧠 System-Level Backend Depth (Implemented in this repo)

This backend includes system-level CLM capabilities (not only endpoint-level features):

### 1) Database schema design (explicit domain modeling)

- **Core CLM entities** are modeled as first-class tables: `Contract`, `ContractVersion`, `ContractClause`, `WorkflowLog`, `ApprovalModel`, `Workflow`, `WorkflowInstance`, and `AuditLogModel`.
- **Tenant-first schema**: critical tables include `tenant_id` and indexes for tenant-scoped query performance.
- **Version-aware uniqueness constraints** exist across templates/clauses/contracts (for example: tenant+name+version, contract+version_number).
- **Hybrid relational + JSON design** supports strict entities plus flexible workflow/config payloads.
- **E-sign trace models** are also explicit (`Signer`, `SigningAuditLog`, `Firma*`, `Inhouse*`) for signature lifecycle state and compliance trails.

### 2) Contract version history + document traceability

- `Contract.current_version` tracks the current working revision.
- `ContractVersion` stores immutable snapshots with:
      - `version_number`
      - storage key (`r2_key`)
      - `template_version`
      - `change_summary`
      - integrity metadata (`file_hash`, `file_size`)
- `ContractClause` snapshots clause-level provenance per version (content + position + alternatives).
- `WorkflowLog` provides contract workflow events (`submitted`, `approved`, `rejected`, `version_created`, etc.).
- API/middleware audit trails are present through:
      - `audit_logs` app (`AuditLogModel`)
      - request-level audit middleware logging
      - e-sign provider-specific immutable signing audit logs.

### 3) Approvals workflow (multi-stage and policy-driven)

- `approvals` + `workflows` modules implement approval state and workflow instances.
- Contracts include approval fields: `approval_chain`, `approval_required`, `current_approvers`, `approved_by`, `approved_at`.
- `ApprovalWorkflowEngine` supports:
      - rule matching by entity conditions
      - configurable approval levels
      - timeouts/escalation flags
      - notification hooks (email + in-app)
      - approval analytics/statistics.

### 4) Role-based access and tenant isolation

- Stateless JWT auth carries tenant/user/admin claims (`tenant_id`, `is_admin`, `is_superadmin`).
- Custom permission classes enforce admin/superadmin authorization (`IsAdminUser`, `IsSuperAdminUser`).
- Global authenticated defaults + endpoint-level permissions across modules.
- Tenant isolation middleware injects tenant context at request time for scoped reads/writes.
- Tenant-aware throttling keys (`tenant_id:user_id`) reduce noisy-neighbor risk.

### 5) Production engineering for async OCR/AI-style workloads

- **Queue system**: Celery integrated with Redis broker/result backend.
- **Async job handling**: AI draft generation is queued and tracked via task records/status.
- **Retry/failure handling**: Celery task retry with backoff (`max_retries`, incremental `countdown`), explicit failed status, error persistence.
- **Task guardrails**: soft/hard execution time limits configured for workers.
- **Caching strategy**:
      - local/dev: `LocMemCache`
      - production: Redis cache backend
      - DRF throttling consumes this cache layer.
- **Degradation strategy**: fail-open throttling mixin prevents cache outages from taking APIs down.

### 6) API design signal (docs, versioning, behavior)

- **OpenAPI/Swagger** is built in via drf-spectacular:
      - `/api/schema/` (OpenAPI)
      - `/api/docs/` (Swagger UI)
- **Path versioning strategy** is already used (`/api/v1/...`) for core product APIs.
- **Auth + docs alignment**: Bearer auth schema is published for interactive testing.
- **Extensive API inventory** is maintained in `docs/BACKEND_API_DOCUMENTATION.md`.
- **Error shapes are documented** (`error`, `detail`, serializer validation maps) with HTTP status semantics.

### 7) Senior backend engineering signals

- **Scaling choices documented**: Supabase transaction pooler mode, connection aging strategy.
- **Infra separation**: Postgres for system-of-record, Redis for cache/queue, R2 for object storage.
- **Observability baseline**: Prometheus metrics, OpenTelemetry hooks, request correlation IDs, slow query logging.
- **Security controls**: strict mode toggles, hardened headers, JWT stateless auth, tenant isolation.
- **Tradeoff-aware defaults**: local developer ergonomics (locmem + optional strictness) with production-focused overrides via environment variables.

### 8) Architecture decisions (ADR-style rationale)

#### Redis + Celery for async task processing

**Decision**: Use Redis as broker + result store; Celery for task orchestration.

**Tradeoffs**:
- ✅ **Horizontal scalability**: workers can scale independently of the main API
- ✅ **Fail-safe**: explicit task retry with exponential backoff; persistence in result store
- ✅ **Dev parity**: tasks run synchronously in DEBUG mode (no Redis needed) via Celery test modes
- ❌ **Operational overhead**: requires Redis uptime; dead-letter handling needs external tooling
- ❌ **Alternative rejected**: long-polling or direct async (Django async views) — insufficient for multi-minute AI/OCR workloads

**Applied to**:
- AI draft generation (multi-step RAG → LLM → embeddings)
- Document OCR/redaction batch jobs
- E-signature status polling

---

#### Path-based API versioning (`/api/v1/...`)

**Decision**: Separate major versions by URL path segment; minor/patch within schemas.

**Tradeoffs**:
- ✅ **Explicit contract versioning**: client routes are permanent; breaking changes are obvious
- ✅ **Backward-compatible deprecation**: old API path stays live until sunsetting
- ✅ **Clear semantic**: consumers can pin stably
- ❌ **URL bloat**: namespace grows with major versions
- ❌ **Alternative rejected**: header-based versioning (Accept-Version) — harder for browser/curl/docs discovery

**Applied to**: all feature endpoints (`/api/v1/contracts/`, `/api/v1/ai/`, etc.)

---

#### Stateless JWT auth (no session DB lookup per-request)

**Decision**: Decode JWT claims into in-memory user context; validate signature only.

**Tradeoffs**:
- ✅ **Zero user state queries**: no DB round-trip per request
- ✅ **Scales to millions of concurrent users**: identity is self-contained
- ✅ **Multi-region/edge ready**: any backend replica can validate
- ❌ **Revocation lag**: token remains valid until expiry (mitigated by short lifetime)
- ❌ **Claim mutations**: role changes may not apply mid-session (acceptable for CLM workflows)

**Applied to**: JWT token carries `user_id`, `email`, `tenant_id`, `is_admin`, `is_superadmin`

---

#### Multi-tenant isolation via row-level scope + middleware injection

**Decision**: Include `tenant_id` in every model; middleware injects it; queries filter by it.

**Tradeoffs**:
- ✅ **Simple + auditable**: every row is explicitly tagged
- ✅ **Impossible to accidentally leak data**: SQL filters are deterministic
- ✅ **No RLS database feature needed**: portable to any SQL database
- ❌ **Developer burden**: `tenant_id` must be threaded everywhere
- ❌ **Alternative rejected**: database RLS (Postgres Row Security) — less portable; harder to test

**Applied to**: all core models include `tenant_id` index + filter in queryset definitions

---

#### Cloudflare R2 for document/artifact storage

**Decision**: S3-compatible object store for contract PDFs, signed documents, versions.

**Tradeoffs**:
- ✅ **Massive scale**: unlimited document count; per-put/get pricing
- ✅ **No server disk bloat**: separation of concerns (DB vs. files)
- ✅ **CDN-able**: public URLs optionally served via Cloudflare edge
- ❌ **Network latency**: every file fetch incurs round-trip to R2
- ❌ **Alternative rejected**: local filesystem (not suitable for multi-server); database BLOB storage (limits query performance)

**Applied to**: `/api/v1/upload-document/`, `/api/v1/contracts/{id}/download/`, e-signature PDFs

---

#### Supabase + PostGIS + pgvector (PostgreSQL + managed services)

**Decision**: Managed Postgres with vector extensions for semantic search; transaction pooler for connection limits.

**Tradeoffs**:
- ✅ **Full-featured SQL**: complex multi-join queries for contract/clause relationships
- ✅ **Vector extensions**: pgvector for semantic similarity without separate embedding DB
- ✅ **Managed operations**: automatic backups, monitoring, scaling
- ❌ **Vendor lock-in**: Supabase-specific pooler mode; migration to self-hosted is non-trivial
- ❌ **Alternative rejected**: MongoDB (weak for CLM relational schema); DynamoDB (overkill for transaction needs)

**Applied to**: all entity storage + semantic search queries

---

#### Prometheus + OpenTelemetry observability baseline

**Decision**: Export metrics to Prometheus; instrument requests with OTel for tracing.

**Tradeoffs**:
- ✅ **Standard observability**: Prometheus is industry-standard; integrates with Grafana
- ✅ **Request correlation**: X-Request-ID propagates through logs; OTel spans link events
- ✅ **Low-overhead**: no agent; client library is lightweight
- ❌ **Operational setup required**: Prometheus scraper + Grafana must be deployed separately
- ❌ **Alternative rejected**: ELK stack (heavyweight for current scale); Datadog (vendor lock-in + cost)

---

#### Emphasis on fail-open + graceful degradation

**Decision**: Cache/queue failures do not break API responses; throttling, rate limits layer.

**Tradeoffs**:
- ✅ **Resilience**: Redis down → requests still work (no cache, but service available)
- ✅ **Local dev friendly**: Redis optional for local debugging
- ✅ **Staged rollout**: can deploy cache layer incrementally
- ❌ **Stale data possible**: cache miss or outage means fresh compute (may be slow)
- ❌ **Harder to diagnose**: failures are silent (logged but not blocking)

**Applied to**: throttle mixin catches cache exceptions; returns 200 if backing cache fails

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

## 📖 Swagger/OpenAPI Documentation

### Access Points

1. **Swagger UI** (Interactive): `http://localhost:8000/api/docs/`
   - Browse all endpoints
   - Test API requests live
   - View request/response examples
   - Copy `curl` commands

2. **ReDoc Documentation**: `http://localhost:8000/api/redoc/`
   - Alternative API documentation interface
   - Better for reading complex schemas

3. **OpenAPI Schema (JSON)**: `http://localhost:8000/api/schema/`
   - Raw OpenAPI 3.0 schema
   - Import into Postman, Insomnia, or other tools

### Tools Used

- **drf-spectacular** (`pip install drf-spectacular`)
  - Auto-generates OpenAPI 3.0 schema from DRF views
  - Zero configuration needed; introspects serializers + permissions
- **Swagger UI** & **ReDoc** bundled with drf-spectacular

### Auto-Documentation Features

**All endpoints are automatically documented**:
- Request/response schemas pulled from serializers
- HTTP status codes (200, 400, 401, 403, 404, 500)
- Query parameters, path parameters, request/response body
- Authentication requirements (Bearer token)
- Pagination + filtering info
- Error responses with examples

**Example endpoint documentation**:
```
GET /api/v1/contracts/
├─ Description: List all contracts (tenant-scoped)
├─ Auth: Bearer token required
├─ Query params:
│  ├─ status: "draft" | "submitted" | "approved" | "signed"
│  ├─ ordering: "-created_at" | "name"
│  └─ page_size: integer (default: 20)
├─ Response 200:
│  {
│    "count": 150,
│    "next": "http://api/v1/contracts/?page=2",
│    "results": [
│      {
│        "id": "uuid",
│        "name": "Service Agreement 2026",
│        "status": "approved",
│        "created_at": "2026-03-20T10:30:00Z",
│        "current_version": 3,
│        "approvers": ["approver@example.com"],
│        ...
│      }
│    ]
│  }
└─ Response 401: Missing/invalid token
```

### Local Development - Generate Schema

```bash
# Auto-generates OpenAPI schema from code
python manage.py spectacular --file schema.yml

# Or REST framework's built-in (less powerful)
python manage.py generateschema --format openapi > schema.json
```

### CI/CD Integration

**In GitHub Actions**, validate OpenAPI schema:
```yaml
- name: Generate & validate OpenAPI schema
  run: |
    python manage.py spectacular --validate
    # Schema is auto-validated during startup
```

### Import to Postman / Insomnia

1. Open Postman → Import
2. Paste: `http://your-backend/api/schema/`
3. All endpoints + auth headers auto-imported
4. Collections organized by app name (contracts, ai, approvals, etc.)

---

## 🔒 Security Layers (Multi-Defense Strategy)

### Layer 1: Transport Security (HTTPS + Headers)

**Production Config** (`SECURITY_STRICT=True`):

```python
# settings.py
SECURE_SSL_REDIRECT = True              # Force HTTPS
SESSION_COOKIE_SECURE = True            # Cookies sent only over HTTPS
CSRF_COOKIE_SECURE = True              # CSRF tokens sent only over HTTPS

# Security headers
SECURE_HSTS_SECONDS = 31536000         # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True             # Include in HSTS preload list

SECURE_CONTENT_SECURITY_POLICY = {     # Mitigate XSS
    "default-src": ("'self'",),
    "script-src": ("'self'", "'unsafe-inline'"),  # Adjust as needed
}

X_FRAME_OPTIONS = "DENY"               # Prevent clickjacking
SECURE_BROWSER_XSS_FILTER = True       # Enable XSS filter in older browsers
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
```

**HTTP Response Headers** (auto-added):
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### Layer 2: Authentication (Stateless JWT)

**JWT Token Structure**:
```json
Header: {
  "alg": "HS256",
  "typ": "JWT"
}

Payload: {
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
  "is_admin": false,
  "is_superadmin": false,
  "roles": ["approver"],
  "exp": 1711449000,
  "iat": 1711448400,
  "jti": "550e8400-e29b-41d4-a716-446655440002"
}

Signature: HMAC-SHA256(base64(header) + "." + base64(payload), SECRET_KEY)
```

**JWT Protection**:
```python
# settings.py
JWT_AUTH = {
    'JWT_SECRET_KEY': os.getenv('DJANGO_SECRET_KEY'),
    'JWT_ALGORITHM': 'HS256',
    'JWT_EXPIRATION_DELTA': timedelta(minutes=15),
    'JWT_ALLOW_REFRESH': True,
    'JWT_REFRESH_EXPIRATION_DELTA': timedelta(days=7),
    'JWT_VERIFY_EXPIRATION': True,
    'JWT_AUTH_HEADER_TYPES': ('Bearer',),
}
```

### Layer 3: Authorization (Role-Based Access Control)

**Permission Classes**:
```python
class IsAuthenticated(permissions.BasePermission):
    """User must have valid JWT token"""

class IsAdminUser(permissions.BasePermission):
    """User must be admin of their tenant"""
    
class IsSuperAdminUser(permissions.BasePermission):
    """User must be superadmin (all tenants)"""

class HasRole(permissions.BasePermission):
    """User must have specific role (approver, editor, viewer)"""
    
class IsTenantMember(permissions.BasePermission):
    """User can only access objects in their tenant"""
```

**Applied in Views**:
```python
class ContractListView(ListAPIView):
    permission_classes = [IsAuthenticated, IsTenantMember]
    
    def get_queryset(self):
        return Contract.objects.filter(tenant_id=self.request.user.tenant_id)

class ContractApprovalView(CreateAPIView):
    permission_classes = [IsAuthenticated, HasRole('approver')]
```

### Layer 4: Rate Limiting & Throttling

**Prevent Brute-Force / DoS**:

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'clm_backend.throttling.TenantAwareScopedThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'auth.login': '5/minute',
        'auth.otp': '10/minute',
        'default': '1000/hour',
        'contracts': '500/hour',
    }
}
```

**Rate Limit Headers**:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 998
X-RateLimit-Reset: 1711452000
Retry-After: 3600
```

### Layer 5: CSRF Protection

**For State-Changing Operations**:

```python
POST /api/v1/contracts/

Headers:
  Authorization: Bearer {jwt_token}
  X-CSRFToken: {csrf_token}
  Content-Type: application/json
```

### Layer 6: Tenant Isolation (Row-Level Security)

**Every model includes** `tenant_id` + index:

```python
class Contract(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    
    class Meta:
        indexes = [
            models.Index(fields=['tenant_id', 'created_at']),
        ]
```

**Middleware enforces filtering**:
```python
def get_queryset(self):
    return self.model.objects.filter(tenant_id=self.request.user.tenant_id)
```

### Layer 7: Input Validation & SQL Injection Prevention

**Django ORM prevents SQL injection**:
```python
# ✅ Safe (parameterized queries)
Contract.objects.filter(name=name)
```

**DRF Serializer Validation**:
```python
class ContractSerializer(serializers.ModelSerializer):
    def validate_name(self, value):
        if len(value) < 3:
            raise serializers.ValidationError("Name too short")
        return value
```

### Layer 8: PII Protection & Audit Logging

**Sensitive fields excluded from logs**:
```python
class MaskPII(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                           '***@***.com', record.msg)
        return True
```

**Immutable Audit Trail**:
```python
class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL)
    action = models.CharField(max_length=50)
    resource_type = models.CharField(max_length=50)
    resource_id = models.UUIDField()
    old_values = models.JSONField()
    new_values = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
```

### Layer 9: Dependency Security

**Automated scanning**:
```bash
pip install safety bandit
safety check requirements.txt
bandit -r . -ll
```

### Layer 10: Environment-Based Controls

**Local Development** (permissive):
```
DEBUG=True
SECURITY_STRICT=False
```

**Production** (strict):
```
DEBUG=False
SECURITY_STRICT=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

### 🛡️ Security Checklist

- ✅ All HTTP traffic → HTTPS redirect
- ✅ JWT tokens cannot be forged (HMAC-SHA256)
- ✅ Tokens expire in 15 minutes (refresh 7 days)
- ✅ Every endpoint requires authentication
- ✅ Role-based access control enforced
- ✅ Tenant isolation at row + SQL level
- ✅ Rate limiting prevents brute-force
- ✅ Input validation prevents injection
- ✅ PII protected in logs
- ✅ Audit trail immutable
- ✅ Dependencies scanned weekly
- ✅ Security headers prevent XSS/clickjacking
- ✅ CSRF tokens required for state-changes

---

## 🔐 Authentication Flows (Detailed)

### JWT Token Flow

```
1. User POSTs credentials to /api/v1/auth/login/
   Request: { "email": "user@example.com", "password": "..." }

2. Backend validates + generates JWT tokens:
   ✅ Short-lived access token (15m)
   ✅ Long-lived refresh token (7d)
   Response: { "access": "eyJ...", "refresh": "eyJ...", "user": {...} }

3. Client stores tokens (memory for access, secure cookie for refresh)

4. Every API request includes:
   Authorization: Bearer {access_token}

5. Backend decodes JWT claims:
   {
     "user_id": "abc123",
     "email": "user@example.com",
     "tenant_id": "tenant456",
     "is_admin": false,
     "is_superadmin": false,
     "roles": ["approver", "viewer"]
   }

6. Middleware injects user context; every view accesses request.user

7. Token expires → client POSTs refresh token to /api/v1/auth/refresh/
   Request: { "refresh": "eyJ..." }
   Response: { "access": "eyJ..." } (new short-lived token)
```

### OTP Verification Flow (High-Security Operations)

```
1. User POSTs email to /api/v1/auth/request-otp/
   Request: { "email": "user@example.com" }

2. Backend generates OTP + sends via email
   Sent to: user@example.com
   OTP valid for: 10 minutes

3. User receives email, copies OTP

4. User POSTs OTP to /api/v1/auth/verify-otp/
   Request: { "email": "user@example.com", "otp": "123456", "purpose": "contract_signing" }

5. Backend validates OTP + generates OTP token (short-lived, single-use)
   Response: { "otp_token": "eyJ...", "expires_in": 600 }

6. Client uses OTP token for sensitive operations (e.g., contract signing)
   Authorization: Bearer {otp_token}
```

### Google OAuth Flow (Optional)

```
1. Frontend redirects to /api/v1/auth/google/

2. User signs in with Google

3. Google redirects back with auth code

4. Backend exchanges code for Google ID token

5. Backend either creates or updates user account

6. Backend returns JWT tokens (same as login flow)
   Response: { "access": "eyJ...", "refresh": "eyJ..." }
```

### Role-Based Access Control (RBAC)

**Roles hierarchy**:
- `superadmin` — system administrator (all tenants)
- `admin` — tenant administrator
- `approver` — can approve contracts
- `editor` — can edit contracts
- `viewer` — read-only access

**Applied via middleware + permission classes**:

```python
# In views.py
class ContractDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsAdminOrEditor]
    # Only users with admin/editor role can edit
    
class ContractApprovalView(CreateAPIView):
    permission_classes = [IsAuthenticated, HasRole('approver')]
    # Only approvers can approve
```

**Token validation happens at middleware level** → claim validation is zero-cost → all downstream requests assume valid context.

---

## � DevOps & Lifecycle Practices

### Versioning Strategy

- **Semantic Versioning** for releases: `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- **Tags** in Git: `v1.2.3` for release commits
- **Database migrations** are versioned per deployment (Django migrations)
- **API versioning**: path-based (`/api/v1/`, `/api/v2/`) for breaking changes
- **Contract schema versioning**: immutable snapshots stored per `contract_version`

### CI/CD Pipeline

**GitHub Actions workflows** (recommended setup):

```yaml
# On PR:
- Lint (flake8, black)
- Type check (mypy)
- Run full test suite
- Coverage reports
- Security scan (bandit)

# On merge to main:
- Build Docker image
- Push to registry
- Deploy to staging
- Run smoke tests
- Deploy to production (manual approval)
```

**Tools**:
- **Code quality**: flake8, black, isort
- **Type safety**: mypy
- **Security**: bandit, safety (deps)
- **Testing**: pytest, coverage
- **Container**: Docker + Docker Compose

### Branching Workflow

```
main (production)
  └── staging (pre-prod)
      └── feature/* (dev branches)
```

**Rules**:
- PRs require code review + passing tests
- `main` is always deployable
- `staging` mirrors production environment
- Feature branches: `feature/contract-versioning`, `fix/auth-token-bug`
- Commits: descriptive messages (`feat: add clause classification`, `fix: race condition in approvals`)

### Environment Management

| Environment | Purpose | Auto-deploy | Details |
|---|---|---|---|
| **local** | Developer machine | N/A | `DEBUG=True`, in-memory cache, SQLite optional |
| **dev** | Shared dev server | On push to `dev` branch | Real Postgres, Redis, Celery workers |
| **staging** | Pre-production mirror | On PR merge to `staging` | Same config as prod, full data sanitization |
| **production** | Live system | Manual + approval gates | Monitoring, backups, strict security |

### Release Process

1. **Bump version** in `__init__.py` or `setup.py`
2. **Run full test suite** locally + in CI
3. **Create release branch**: `release/v1.2.3`
4. **Generate changelog** with commit history
5. **Tag commit**: `git tag v1.2.3`
6. **Deploy to staging** for final smoke tests
7. **Deploy to production** with canary or blue-green strategy
8. **Monitor logs** + metrics for 24 hours
9. **Post-mortem** if issues; rollback if needed

---

## ✅ Production Readiness Checklist

### Code Quality & Architecture

- ✅ **Modular design**: apps are loosely coupled, each with clear responsibilities
  - `authentication/`: JWT + OTP
  - `contracts/`: core CLM entity management
  - `ai/`: AI service integrations
  - `approvals/`: workflow engine
  - `audit_logs/`: immutable audit trail
- ✅ **Layered architecture**: models → serializers → views → URLs
  - Business logic in services (`approval_engine.py`, `ai_service.py`)
  - View layer thin (delegation to services)
- ✅ **Dependency injection**: explicit parameter passing, not hidden globals
- ✅ **No tight coupling**: swappable backends (e.g., AI providers, cache)

### Testing & Code Coverage

- ✅ **Unit tests** for all business logic
  - `tests/test_approvals.py`, `tests/test_contracts.py`
  - Target: >80% coverage on critical paths
- ✅ **Integration tests** for API endpoints
  - Database transactions tested end-to-end
  - Auth flows verified with real tokens
- ✅ **Production tests** in `tests/README_PRODUCTION_TESTS.md`
  - Smoke tests run post-deploy
  - Synthetic transaction monitoring
- ✅ **Test fixtures** for common data scenarios
- ✅ **Continuous coverage monitoring** via CI

### Validation & Input Handling

- ✅ **Strong validation** at all entry points
  - Serializers (`serializers.py` in each app)
  - Custom validators for business rules
  - JSON schema validation for flexible fields
- ✅ **Error normalization**: all endpoints return consistent error shape
  - `{"error": "...", "detail": "...", "status_code": ...}`
- ✅ **Rate limiting** per user + tenant to prevent abuse
- ✅ **SQL injection prevention**: parameterized queries (ORM enforced)

### Security

- ✅ **Authentication**: JWT tokens with short expiry (15m) + refresh tokens (7d)
- ✅ **Authorization**: role-based permissions on every endpoint
- ✅ **Tenant isolation**: row-level filtering, impossible to leak cross-tenant data
- ✅ **PII protection**: sensitive fields logged only if necessary; audit trail tracks access
- ✅ **HTTPS only** in production
- ✅ **CSRF tokens** for state-changing requests
- ✅ **Security headers**: CSP, X-Frame-Options, HSTS
- ✅ **Dependency scanning**: regular updates, security patches

### Observability

- ✅ **Structured logging** with request context
  - Request ID propagation
  - Tenant context in all logs
- ✅ **Metrics** exported to Prometheus
  - Request latency, error rates, queue depth
- ✅ **Distributed tracing** via OpenTelemetry
- ✅ **Alerting** configured for critical errors
- ✅ **Error tracking** (optional Sentry integration)

### Database & State Management

- ✅ **Migrations tracked** in version control
- ✅ **Backup strategy** documented (automated daily snapshots)
- ✅ **Data retention policies** enforced
- ✅ **Connection pooling** tuned for scale
- ✅ **Recovery time objective (RTO)** documented

### API Design & Documentation

- ✅ **OpenAPI schema** auto-generated (`/api/schema/`)
- ✅ **Swagger UI** at `/api/docs/`
- ✅ **Comprehensive API documentation**: `docs/BACKEND_API_DOCUMENTATION.md`
- ✅ **Error codes** documented (e.g., `INVALID_CONTRACT_STATE`, `APPROVAL_TIMEOUT`)
- ✅ **Rate limit headers** included in responses

---

## 🧪 Testing Strategy

### Test Hierarchy

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  E2E Tests (slow, few)                                                              │  Rare, only critical flows
│  └─ Full workflow tests                                                             │  (e.g., contract submission → approval)
├────────────────────────────────────────────────────────────────────────────────────┤
│  Integration Tests (medium, some)                                                   │  API endpoints + service layer
│  └─ API + Database + External services                                              │  Celery task execution
├────────────────────────────────────────────────────────────────────────────────────┤
│  Unit Tests (fast, many)                                                            │  Business logic, validators
│  └─ Functions, classes in isolation                                                 │  Serializers, services
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Running Tests Locally

```bash
# All tests (unit + integration)
python manage.py test

# Specific app
python manage.py test contracts

# With coverage
python -m pytest --cov=contracts --cov-report=html

# Integration tests only
python manage.py test tests/integration/

# Production smoke tests
python manage.py test tests/README_PRODUCTION_TESTS.md
```

### Test Files

- `contracts/tests.py` — Contract CRUD, versioning, state transitions
- `ai/test_advanced_features.py` — Metadata extraction, summarization
- `audit_logs/test_audit_logging.py` — Audit trail immutability
- `approvals/tests.py` — Workflow logic, approval chains
- `authentication/tests.py` — JWT flow, OTP, role validation
- `tests/production_tests.py` — Smoke tests, synthetic transactions

### Mocking Strategy

- **External AI APIs** (Gemini, VoyageAI): mock via `unittest.mock`
- **Email/notifications**: capture in test mailbox
- **Celery tasks**: run synchronously in tests (`CELERY_ALWAYS_EAGER=True`)
- **R2 storage**: use local filesystem stub for tests

---

## �🚀 Production Deployment

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

## 📚 Documentation & Resources

### Backend Documentation

- **Full API Reference**: [BACKEND_API_DOCUMENTATION.md](docs/BACKEND_API_DOCUMENTATION.md)
  - All endpoints, request/response schemas, examples
- **Feature Index**: [FEATURES_INDEX.md](docs/FEATURES_INDEX.md)
  - Complete list of implemented features + status
- **Admin Guide**: [admin.md](docs/admin.md)
  - Admin-only endpoints, user management, tenant setup
- **AI Features**: [ai.md](docs/ai.md)
  - Metadata extraction, summarization, classification
- **Authentication**: [authentication.md](docs/authentication.md)
  - JWT flows, OTP, OAuth, role-based access
- **Workflows & Approvals**: [workflows.md](docs/workflows.md)
  - Approval chains, state transitions, notifications
- **Audit Logging**: [audit_logs](docs/)
  - Immutability, retention, compliance
- **Production Tests**: [README_PRODUCTION_TESTS.md](tests/README_PRODUCTION_TESTS.md)
  - Smoke tests, synthetic monitoring

### Frontend Repository

**Companion Frontend (React/Next.js)**:
- 📱 GitHub: [vk93102/Contracts-Life-Cycle-Management-Frontend](https://github.com/vk93102/Contracts-Life-Cycle-Management-Frontend)
- Features: Contract upload/viewing, approval workflows, AI insights, audit logs
- Integrates with this backend via REST API + JWT

### Environment Setup Guide

**Local Development**:
```bash
# Clone repo
git clone https://github.com/yourusername/Contracts-Life-Cycle-Management-Backend.git
cd Contracts-Life-Cycle-Management-Backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up local environment
cp .env.example .env
# Edit .env with local values (Redis optional for local dev)

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver

# In separate terminal, start Celery worker (optional for background tasks)
celery -A clm_backend worker --loglevel=info
```

**Docker Setup**:
```bash
docker-compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
# Access at http://localhost:8000
```

### Deployment Instructions

**Prerequisites**:
- [ ] Supabase or PostgreSQL instance with pgvector + pg_trgm extensions
- [ ] Redis instance (for caching + Celery)
- [ ] Cloudflare R2 account (for document storage)
- [ ] Gemini API key (for AI features)
- [ ] VoyageAI API key (for embeddings)
- [ ] SMTP server (for email notifications)

**Deploy to Heroku (example)**:
```bash
# Create Heroku app
heroku create your-clm-app

# Set environment variables
heroku config:set DEBUG=False
heroku config:set DJANGO_SECRET_KEY=<generated-key>
heroku config:set DATABASE_URL=<supabase-url>
# ... set all required env vars

# Push to Heroku
git push heroku main

# Run migrations
heroku run python manage.py migrate

# Collect static files
heroku run python manage.py collectstatic

# Scale workers
heroku ps:scale web=2 worker=1
```

**Deploy to AWS EC2/ECS**:
1. Build Docker image: `docker build -t clm-backend .`
2. Push to ECR: `aws ecr get-login-password | docker login ...`
3. Deploy via CloudFormation or ECS console
4. Set environment variables in task definition
5. Use RDS for PostgreSQL + ElastiCache for Redis
6. Enable CloudWatch monitoring

**Post-deployment**:
- [ ] Run smoke tests: `python manage.py test tests/production_tests.py`
- [ ] Verify `/api/docs/` is accessible
- [ ] Check `/metrics` for Prometheus
- [ ] Test JWT auth flow with real credentials
- [ ] Monitor logs for 24 hours


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

**Enterprise Contract Lifecycle Management Backend**

**Built with ❤️ using Django & Django REST Framework**

---

### 📦 Related Repositories

| Repository | Purpose | Language | Status |
|---|---|---|---|
| [**Backend** (this repo)](https://github.com/vk93102/Contracts-Life-Cycle-Management-Backend) | REST API, AI integration, database | Python/Django | ✅ Production |
| [**Frontend**](https://github.com/vk93102/Contracts-Life-Cycle-Management-Frontend) | UI, contract management, workflows | React/Next.js | ✅ Production |

---

### 🎬 Resources

- **[📹 Live Demo Video](https://www.loom.com/share/694dee3f381545b2a17f2dc1831c5bd0)** - See the system in action
- **[🔧 Backend Setup](https://github.com/vk93102/Contracts-Life-Cycle-Management-Backend)** - Django REST API
- **[🎨 Frontend Setup](https://github.com/vk93102/Contracts-Life-Cycle-Management-Frontend)** - React/Next.js UI

---

**Quick Links**: [API Docs](docs/) • [Feature Index](docs/FEATURES_INDEX.md) • [Deployment Guide](#deployment-instructions) • [Contributing](#-contributing) • [License](#-license)

</div>

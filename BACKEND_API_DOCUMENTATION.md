# CLM Backend API Documentation

This document describes the **currently mounted** API endpoints in this Django/DRF backend, including authentication, tenant scoping, admin permissions, and feature modules.

> Source of truth for routing: `clm_backend/urls.py` plus each app’s `urls.py`.

---

## Base URLs

- **Admin UI**: `GET /admin/`
- **Metrics**: `GET /metrics`
- **Auth**: `/api/auth/*`
- **Versioned API**: `/api/v1/*`
- **Search API (frontend uses this)**: `/api/search/*`
- **Notifications (legacy prefix)**: `/api/notifications/*`

---

## Authentication

### JWT auth (default)
The API uses **SimpleJWT** with a **stateless user** built from JWT claims (no DB lookup per request).

Send this header on authenticated endpoints:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

Token claims used throughout the backend:

- `user_id`: UUID (string)
- `email`: string
- `tenant_id`: UUID (string)
- `is_admin`: boolean
- `is_superadmin`: boolean

### Token lifetimes
Configured in `SIMPLE_JWT`:

- Access token lifetime: 24 hours
- Refresh token lifetime: 7 days

### Tenant isolation
Most endpoints are tenant-scoped by `request.user.tenant_id` (also injected into `request.tenant_id` by middleware).

Important behaviors:

- If `tenant_id` is missing from the token/user context, many endpoints will return `400` or empty results.
- Contract listing is additionally **user-scoped** for non-admin users.

### Admin vs Superadmin
Permissions used by admin endpoints:

- **Admin**: `is_admin` claim OR `is_staff`/`is_superuser`
- **Superadmin**: `is_superadmin` claim OR `is_superuser`

### Bootstrap admin (dev/staging convenience)
In `DEBUG` (or when `ENABLE_BOOTSTRAP_ADMINS=true`), users whose email is allowlisted in `BOOTSTRAP_ADMIN_EMAILS` are automatically promoted to `is_staff` at login/register.

Defaults include:

- `rahuljha93102@gmail.com`

---

## Pagination
List endpoints that use DRF pagination return:

```json
{
  "count": 123,
  "next": "https://.../?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Default page size: **50**.

---

## Rate limiting (throttling)
Global throttles are enabled.
Key scopes (see `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`):

- `auth`: 10/min
- `ai`: 30/min
- `uploads`: 20/min
- `firma`: 120/min

---

## Error responses
This backend commonly returns one of:

- `{ "error": "..." }`
- `{ "detail": "..." }`
- DRF serializer errors: `{ "field": ["msg"] }`

---

# Endpoints

## Health & Monitoring

### Health
- `GET /api/v1/health/`

### Metrics (Prometheus)
- `GET /metrics`
  - Optional auth: if `METRICS_TOKEN` is set, include header `X-Metrics-Token: <token>`

---

## Auth (`/api/auth/`)

- `POST /api/auth/login/`
  - Body: `{ "email": "...", "password": "..." }`
  - Returns: `{ access, refresh, user }`
  - If account inactive, returns `403` with `pending_verification: true`

- `POST /api/auth/register/`
  - Body: `{ "email": "...", "password": "...", "full_name": "...", "company": "...", "tenant_id"?: "...", "tenant_domain"?: "..." }`
  - Returns: `pending_verification: true` and sends OTP

- `POST /api/auth/google/`
  - Google OAuth login (expects an ID token)

- `GET /api/auth/me/`
  - Current authenticated user context

- `POST /api/auth/token/refresh/`
  - SimpleJWT refresh endpoint

- `POST /api/auth/forgot-password/`
- `POST /api/auth/reset-password/`
- `POST /api/auth/logout/`
- `POST /api/auth/refresh/`
- `POST /api/auth/verify-password-reset-otp/`
- `POST /api/auth/resend-password-reset-otp/`
- `POST /api/auth/request-login-otp/`
- `POST /api/auth/verify-email-otp/`

---

## Admin (`/api/v1/admin/`)
All endpoints require `IsAuthenticated` + admin permissions.

- `GET /api/v1/admin/me/`

- `GET /api/v1/admin/users/?q=<search>&all_tenants=1|0`
  - `all_tenants=1` only works for superadmins

- `POST /api/v1/admin/users/promote/?all_tenants=1|0`
  - Superadmin-only
  - Body: `{ "user_id"?: "...", "email"?: "..." }`

- `POST /api/v1/admin/users/demote/?all_tenants=1|0`
  - Superadmin-only
  - Body: `{ "user_id"?: "...", "email"?: "..." }`

- `GET /api/v1/admin/analytics/`
- `GET /api/v1/admin/activity/`
- `GET /api/v1/admin/feature-usage/`
- `GET /api/v1/admin/user-registration/`
- `GET /api/v1/admin/user-feature-usage/`

---

## Dashboard (`/api/v1/`)

- `GET /api/v1/dashboard/insights/`
  - Returns: per-user tenant-scoped usage KPIs, activity trend, contract/review/calendar/esign usage.

---

## Notifications (`/api/`)

- `GET /api/notifications/`
- `POST /api/notifications/`
- `GET /api/notifications/{id}/`
- `PATCH /api/notifications/{id}/`
- `DELETE /api/notifications/{id}/`

---

## Repository & Documents (`/api/v1/`)

### Repository router endpoints
- `/api/v1/repository/`
- `/api/v1/repository/{id}/`

- `/api/v1/repository-folders/`
- `/api/v1/repository-folders/{id}/`

- `/api/v1/documents/`
- `/api/v1/documents/{id}/`

- `/api/v1/search/`
  - Repository-scoped search endpoints (distinct from `/api/search/*`)

### Private uploads (R2)
- `GET|POST /api/v1/private-uploads/`
- `POST /api/v1/private-uploads/url/`

---

## Contracts, Templates, Clauses, PDF (`/api/v1/`)

### Router (standard DRF ViewSets)
These follow DRF conventions: `GET list`, `POST create`, `GET retrieve`, `PUT/PATCH update`, `DELETE destroy`.

- `/api/v1/contracts/`
- `/api/v1/contracts/{id}/`
  - **Important**: for non-admins, list/detail is scoped to:
    - contracts created by the user, OR
    - contracts where the user is in `current_approvers`
  - `DELETE`:
    - non-admins can delete only their own contracts
    - non-admins cannot delete `status=executed`
    - best-effort Cloudflare R2 cleanup occurs after DB delete

- `/api/v1/contract-templates/`
- `/api/v1/contract-templates/{id}/`

- `/api/v1/clauses/`
- `/api/v1/clauses/{id}/`

- `/api/v1/generation-jobs/`
- `/api/v1/generation-jobs/{id}/`

### Template management (DB-backed template files)
- `GET /api/v1/templates/types/`
- `GET /api/v1/templates/types/{template_type}/`

- `GET /api/v1/templates/files/`
- `GET /api/v1/templates/files/mine/`

- `GET /api/v1/templates/files/schema/{filename}/`
- `GET /api/v1/templates/files/content/{filename}/`

- `GET|POST /api/v1/templates/files/signature-fields-config/{filename}/`
- `POST /api/v1/templates/files/drag-signature-positions/{filename}/`
- `DELETE|POST /api/v1/templates/files/delete/{filename}/`

- `GET /api/v1/templates/summary/`
- `POST /api/v1/templates/create-from-type/`
- `POST /api/v1/templates/validate/`

- `GET /api/v1/templates/user/`
- `DELETE /api/v1/templates/{template_id}/`

- `GET /api/v1/templates/files/{template_type}/`
  - Kept last in routing to avoid shadowing other template endpoints

### PDF generation
- `GET /api/v1/{template_id}/download-pdf/`
- `POST /api/v1/batch-generate-pdf/`
- `GET /api/v1/pdf-generation-status/`

### Cloudflare R2 document utilities
- `POST /api/v1/upload-document/`
- `POST /api/v1/upload-contract-document/`
- `POST /api/v1/document-download-url/`
- `GET /api/v1/{contract_id}/download-url/`

---

## E-sign (SignNow) (`/api/v1/`)

- `POST /api/v1/contracts/upload/`
- `POST /api/v1/esign/send/`
- `GET /api/v1/esign/signing-url/{contract_id}/`
- `GET /api/v1/esign/status/{contract_id}/`
- `GET /api/v1/esign/executed/{contract_id}/`

---

## E-sign (Firma) (`/api/v1/`)

### Core flow
- `POST /api/v1/firma/sign/`
- `POST /api/v1/firma/contracts/upload/`
- `POST /api/v1/firma/esign/send/`
- `POST /api/v1/firma/esign/invite-all/`

- `GET /api/v1/firma/esign/signing-url/{contract_id}/`
- `GET /api/v1/firma/esign/status/{contract_id}/`
- `GET /api/v1/firma/esign/executed/{contract_id}/`
- `GET /api/v1/firma/esign/certificate/{contract_id}/`

### Signing request management
- `GET /api/v1/firma/esign/requests/`
- `DELETE /api/v1/firma/esign/requests/{record_id}/`
  - Deletes the **local tracking record** (`FirmaSignatureContract`)
  - Non-admins can only delete requests for contracts they created
  - Completed requests are blocked (returns `409`)

- `GET /api/v1/firma/esign/details/{contract_id}/`
- `GET /api/v1/firma/esign/reminders/{contract_id}/`
- `GET /api/v1/firma/esign/activity/{contract_id}/`
- `POST /api/v1/firma/esign/resend/{contract_id}/`

### Webhooks
- `GET|POST /api/v1/firma/webhooks/`
- `GET|DELETE /api/v1/firma/webhooks/{webhook_id}/`
- `GET /api/v1/firma/webhooks/secret-status/`

- `POST /api/v1/firma/webhooks/receive/`
  - Vendor callback (no auth)

- `GET /api/v1/firma/webhooks/stream/{contract_id}/`
  - Authenticated stream endpoint used by UI for realtime updates

### JWT helpers (Firma)
- `POST /api/v1/firma/jwt/template/generate/`
- `POST /api/v1/firma/jwt/template/revoke/`
- `POST /api/v1/firma/jwt/signing-request/generate/`
- `POST /api/v1/firma/jwt/signing-request/revoke/`

### Debug
- `GET /api/v1/firma/debug/config/`
- `GET /api/v1/firma/debug/connectivity/`

---

## AI (`/api/v1/`)

- `/api/v1/ai/`
- `/api/v1/ai/{id}/`

(Methods depend on the viewset; standard DRF router behavior applies.)

---

## Reviews (`/api/v1/`)

- `/api/v1/review-contracts/`
- `/api/v1/review-contracts/{id}/`

- `/api/v1/clause-library/`
- `/api/v1/clause-library/{id}/`

---

## Calendar events (`/api/v1/`)

- `/api/v1/events/`
- `/api/v1/events/{id}/`

---

## Workflows (`/api/v1/`)

- `/api/v1/workflows/`
- `/api/v1/workflows/{id}/`

- `/api/v1/workflow-instances/`
- `/api/v1/workflow-instances/{id}/`

---

## Approvals (`/api/v1/`)

- `/api/v1/approvals/`
- `/api/v1/approvals/{id}/`

---

## Search (`/api/search/`)

- `GET /api/search/?q=<query>`
- `GET /api/search/semantic/?q=<query>`
- `POST /api/search/hybrid/`
- `POST /api/search/advanced/`
- `GET /api/search/facets/`
- `POST /api/search/faceted/`
- `GET /api/search/suggestions/?q=<query>`
- `GET|POST|DELETE /api/search/index/`
- `GET /api/search/analytics/`
- `GET|POST /api/search/similar/`

---

# Not currently mounted (present in repo)

The following apps have `urls.py` in the repo but are **not included** in `clm_backend/urls.py` right now, so they are not reachable unless wired in:

- `tenants/urls.py` (tenant CRUD)
- `audit_logs/urls.py`
- `metadata/urls.py`
- `ocr/urls.py`
- `redaction/urls.py`
- `rules/urls.py`
- `nda/urls.py` (NDA workflow)

If you want these exposed, add `path('api/v1/', include('<app>.urls'))` entries in the root URL config.

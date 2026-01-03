# CLM Backend - Django API

A Contract Lifecycle Management (CLM) platform backend built with Django, Supabase (Auth + Postgres), and Cloudflare R2.

## 🚀 Features

### Week 1 - Core Foundation
- ✅ Health check endpoint
- ✅ Supabase JWT authentication with tenant context
- ✅ Create contracts with file uploads (multipart/form-data)
- ✅ List contracts with tenant isolation
- ✅ Cloudflare R2 integration for secure file storage

### Week 2 - Workflows & Controls
- ✅ Contract detail view with signed download URLs
- ✅ Submit contracts for approval
- ✅ Approve/reject workflow
- ✅ Delete contracts with file cleanup
- ✅ Complete audit trail via WorkflowLog

## 📦 Deployment

### Render.com Deployment

1. **Environment Variables** (set these as secrets in Render):
   - `DJANGO_SECRET_KEY`: Your Django secret key
   - `JWT_SECRET_KEY`: Your JWT secret key
   - `DB_NAME`: postgres
   - `DB_USER`: Your Supabase database user
   - `DB_PASSWORD`: Your Supabase database password
   - `DB_HOST`: Your Supabase database host
   - `DB_PORT`: 5432
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_ANON_KEY`: Your Supabase anonymous key
   - `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key

2. **Deploy Options**:
   - Use `render.yaml` for automated deployment
   - Or use `build.sh` + `Procfile` for manual configuration

3. **Start Command**: `gunicorn clm_backend.wsgi:application --bind 0.0.0.0:$PORT`

## 🏗️ Architecture

- **Authentication**: Supabase JWT (HS256) with tenant isolation
- **Database**: Supabase Postgres with RLS-ready models
- **File Storage**: Cloudflare R2 (S3-compatible) with presigned URLs
- **Framework**: Django 5.0 + Django REST Framework

## 📦 Installation

### Prerequisites
- Python 3.11+
- Supabase account with a project
- Cloudflare R2 bucket

### Setup

1. **Clone the repository**
```bash
cd backend
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

5. **Run migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

6. **Run development server**
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000`

## 🔐 Environment Variables

See [.env.example](.env.example) for all required configuration.

### Supabase Setup
1. Create a Supabase project
2. Get your credentials from Settings > API
3. Set up the following in your `.env`:
   - `SUPABASE_URL`: Your project URL
   - `SUPABASE_KEY`: Your anon/public key
   - `SUPABASE_JWT_SECRET`: JWT secret from Settings > API > JWT Settings
   - Database credentials from Settings > Database

### Cloudflare R2 Setup
1. Create an R2 bucket in Cloudflare
2. Create API tokens with R2 permissions
3. Set in `.env`:
   - `R2_ACCOUNT_ID`: Your Cloudflare account ID
   - `R2_ACCESS_KEY_ID`: R2 access key
   - `R2_SECRET_ACCESS_KEY`: R2 secret key
   - `R2_BUCKET_NAME`: Your bucket name

## 📡 API Endpoints

### Authentication
- `GET /api/v1/auth/me/` - Get current user with tenant context

### Health
- `GET /api/v1/health/` - Health check

### Contracts (Week 1)
- `POST /api/v1/contracts/` - Create contract with file upload
- `GET /api/v1/contracts/` - List all contracts (tenant-filtered)

### Contracts (Week 2)
- `GET /api/v1/contracts/{id}/` - Get contract details with download URL
- `POST /api/v1/contracts/{id}/submit/` - Submit for approval
- `POST /api/v1/contracts/{id}/decide/` - Approve/reject contract
- `DELETE /api/v1/contracts/{id}/delete/` - Delete contract

## 📝 API Examples

### Create Contract
```bash
curl -X POST http://localhost:8000/api/v1/contracts/ \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT" \
  -F "file=@contract.pdf" \
  -F "title=NDA for Vendor X" \
  -F "status=draft" \
  -F "counterparty=Vendor X Inc"
```

### List Contracts
```bash
curl -X GET http://localhost:8000/api/v1/auth/me/ \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT"
```

### Submit for Approval
```bash
curl -X POST http://localhost:8000/api/v1/contracts/{id}/submit/ \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT"
```

### Approve/Reject
```bash
curl -X POST http://localhost:8000/api/v1/contracts/{id}/decide/ \
  -H "Authorization: Bearer YOUR_SUPABASE_JWT" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "comment": "Looks good"}'
```

## 🗄️ Database Models

### Contract
- `id` (UUID) - Primary key
- `tenant_id` (UUID) - For RLS/multi-tenancy
- `title` - Contract title
- `r2_key` - File path in R2 storage
- `status` - draft | pending | approved | rejected | executed
- `created_by` - User ID
- `counterparty` - Counterparty name
- `contract_type` - NDA, MSA, etc.
- `value` - Contract value
- `start_date` / `end_date` - Contract dates

### WorkflowLog
- `id` (UUID) - Primary key
- `contract` - Foreign key to Contract
- `action` - created | submitted | approved | rejected | deleted
- `performed_by` - User ID
- `comment` - Optional comment
- `timestamp` - Auto timestamp

## 🔒 Multi-Tenancy & Security

- All requests require Supabase JWT authentication
- `tenant_id` extracted from JWT `user_metadata`
- All contract queries filtered by `tenant_id` (RLS pattern)
- File storage uses tenant-prefixed paths: `{tenant_id}/contracts/{uuid}.pdf`
- Download URLs are presigned (1-hour expiration)

## 🚀 Deployment

### Production Checklist
- [ ] Set `DEBUG=False` in production
- [ ] Generate secure `DJANGO_SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set up HTTPS
- [ ] Enable Supabase RLS policies on database
- [ ] Configure CORS properly
- [ ] Use environment-specific `.env` files

### Run with Gunicorn
```bash
gunicorn clm_backend.wsgi:application --bind 0.0.0.0:8000
```

## 📚 Tech Stack

- **Django 5.0** - Web framework
- **Django REST Framework** - API framework
- **Supabase** - Auth + Postgres database
- **Cloudflare R2** - Object storage (S3-compatible)
- **boto3** - AWS SDK for R2 integration
- **PyJWT** - JWT token handling

## 🤝 Contributing

This is an MVP implementation. For production:
1. Add comprehensive tests
2. Implement proper RLS policies in Supabase
3. Add rate limiting
4. Implement proper error logging
5. Add API documentation (Swagger/OpenAPI)
6. Add pagination for list endpoints

## 📄 License

MIT License

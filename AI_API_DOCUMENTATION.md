# AI-Powered CLM System - API Documentation

## Overview

This document provides comprehensive documentation for all AI-powered endpoints in the Contract Lifecycle Management (CLM) system.

### Technology Stack

- **AI Model**: Google Gemini API (text-embedding-004, gemini-pro)
- **Background Tasks**: django-background-tasks (Database-backed queue, no Redis required)
- **Search**: Hybrid (PostgreSQL Full-Text Search + Vector Similarity with RRF merging)
- **PII Protection**: Regex-based redaction before sending to LLM
- **OCR**: Pillow + pytesseract for document text extraction
- **Email**: Gmail SMTP for notifications
- **Database**: PostgreSQL (Supabase) with vector support

---

## Authentication

All endpoints require JWT authentication.

### Login

```http
POST /api/auth/login/
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Headers for authenticated requests:**
```http
Authorization: Bearer <access_token>
```

---

## AI Endpoints

### 1. Contract Generation

Start async AI-powered contract generation with Chain-of-Thought prompting.

**Endpoint:** `POST /api/generation/start/`

**Request:**
```json
{
  "title": "Service Agreement",
  "contract_type": "MSA",
  "description": "Master Service Agreement for software development",
  "variables": {
    "party_a": "Acme Corp",
    "party_b": "Client Inc",
    "effective_date": "2024-01-15",
    "term": "12 months",
    "payment_amount": "$50,000",
    "payment_terms": "Net 30"
  },
  "special_instructions": "Include IP ownership clause and termination for convenience"
}
```

**Response (202 Accepted):**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Contract generation started. You will be notified when ready."
}
```

**Process:**
1. PII redaction from variables
2. Chain-of-Thought outline generation
3. Full content generation based on outline
4. Self-review for confidence scoring
5. Rule-based validation
6. PII restoration
7. Embedding generation for search
8. Email notification sent

---

### 2. Check Generation Status

Monitor the progress of contract generation.

**Endpoint:** `GET /api/generation/{contract_id}/status/`

**Response (Processing):**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing"
}
```

**Response (Completed):**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "confidence_score": 0.85,
  "generated_text": "MASTER SERVICE AGREEMENT\n\nThis Master Service Agreement..."
}
```

**Response (Failed):**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": "Gemini API rate limit exceeded"
}
```

---

### 3. Hybrid Search

Search contracts using hybrid algorithm combining semantic (vector) and keyword search with Reciprocal Rank Fusion (RRF).

**Endpoint:** `POST /api/search/global/`

**Request:**
```json
{
  "query": "confidentiality non-disclosure",
  "mode": "hybrid",
  "filters": {
    "contract_type": "NDA",
    "status": "active"
  },
  "limit": 10
}
```

**Modes:**
- `hybrid`: Combines vector + keyword search (recommended)
- `semantic`: Vector similarity only (best for concept matching)
- `keyword`: PostgreSQL FTS only (fastest)

**Response:**
```json
{
  "results": [
    {
      "id": "contract-uuid-1",
      "title": "Mutual NDA with Acme Corp",
      "score": 0.892,
      "match_type": "hybrid_rrf",
      "contract": {
        "id": "contract-uuid-1",
        "title": "Mutual NDA with Acme Corp",
        "contract_type": "NDA",
        "status": "active",
        "created_at": "2024-01-15T10:30:00Z"
      }
    }
  ],
  "total": 25,
  "mode": "hybrid",
  "query": "confidentiality non-disclosure"
}
```

**Algorithm Details:**
- **Step 1**: Generate query embedding using Gemini (768 dimensions)
- **Step 2**: Vector search using cosine similarity
- **Step 3**: PostgreSQL FTS with tsvector ranking
- **Step 4**: Merge results using RRF: `score = Σ[weight / (k + rank)]`
- **k constant**: 60 (optimal for legal documents)
- **Default weights**: 60% vector, 40% keyword

---

### 4. Contract Comparison

AI-powered comparison of two contracts highlighting differences and risks.

**Endpoint:** `POST /api/analysis/compare/`

**Request:**
```json
{
  "contract_a_id": "contract-uuid-1",
  "contract_b_id": "contract-uuid-2"
}
```

**Response:**
```json
{
  "summary": "Contract A provides stronger intellectual property protection while Contract B offers more flexible termination terms...",
  "key_differences": [
    "Contract A includes IP assignment clause, Contract B uses licensing",
    "Contract A has 90-day termination notice, Contract B requires 30 days",
    "Contract A limits liability to $100K, Contract B has no cap",
    "Payment terms differ: A is Net 30, B is Net 15"
  ],
  "risk_analysis": {
    "contract_a_advantages": [
      "Comprehensive IP protection",
      "Longer termination notice period"
    ],
    "contract_b_advantages": [
      "More flexible payment terms",
      "Simpler dispute resolution"
    ],
    "contract_a_risks": [
      "No liability cap may expose to unlimited damages"
    ],
    "contract_b_risks": [
      "Weak IP provisions could lead to ownership disputes"
    ]
  },
  "recommendations": "Contract A is more favorable for IP-sensitive work. Consider combining A's IP terms with B's payment flexibility.",
  "raw_analysis": "Full AI response text..."
}
```

---

### 5. Find Related Contracts

Find similar contracts using vector similarity.

**Endpoint:** `GET /api/contracts/{contract_id}/related/`

**Query Parameters:**
- `limit` (optional): Max results (default: 10)

**Response:**
```json
{
  "source_contract": {
    "id": "contract-uuid-1",
    "title": "NDA with Acme Corp"
  },
  "related_contracts": [
    {
      "contract": {
        "id": "contract-uuid-2",
        "title": "NDA with XYZ Inc",
        "contract_type": "NDA"
      },
      "similarity_score": 0.94,
      "contract_type": "NDA",
      "title": "NDA with XYZ Inc"
    },
    {
      "contract": {
        "id": "contract-uuid-3",
        "title": "Confidentiality Agreement"
      },
      "similarity_score": 0.87,
      "contract_type": "NDA",
      "title": "Confidentiality Agreement"
    }
  ]
}
```

**Use Cases:**
- Find contract templates for reuse
- Identify duplicate or redundant contracts
- Discover precedents for similar situations

---

### 6. Document OCR Processing

Trigger OCR processing for uploaded documents (PDFs, images).

**Endpoint:** `POST /api/documents/{document_id}/reprocess/`

**Response:**
```json
{
  "status": "processing",
  "message": "OCR processing started"
}
```

**Check OCR Status:**

**Endpoint:** `GET /api/documents/{document_id}/ocr-status/`

**Response:**
```json
{
  "document_id": "doc-uuid-1",
  "ocr_status": "completed",
  "extracted_text": "This is the extracted text from the document...",
  "text_length": 15432,
  "pages_processed": 5,
  "confidence": 0.92
}
```

**Supported Formats:**
- **Images**: JPG, PNG, GIF, BMP (Tesseract OCR)
- **PDFs**: Multi-page extraction using pdf2image + Tesseract
- **Future**: Handwriting recognition via Google Document AI

---

### 7. Clause Summary

Generate plain-English summary of legal clause.

**Endpoint:** `POST /api/analysis/clause-summary/`

**Request:**
```json
{
  "clause_text": "The Disclosing Party shall not be liable for any indirect, incidental, special, consequential or punitive damages, or any loss of profits or revenues, whether incurred directly or indirectly..."
}
```

**Response:**
```json
{
  "original_text": "The Disclosing Party shall not be liable...",
  "plain_summary": "This clause limits the company's liability. They won't be responsible for indirect damages (lost profits, business interruption) even if they cause the problem. You can only sue for direct, actual damages.",
  "confidence": 0.88,
  "key_points": [
    "Limits liability to direct damages only",
    "Excludes lost profits and business interruption",
    "Applies regardless of fault"
  ]
}
```

---

## Template & Clause Library

### 8. Contract Templates

**List Templates:**
```http
GET /api/templates/

Response:
{
  "results": [
    {
      "id": "template-uuid-1",
      "name": "Standard NDA Template",
      "category": "NDA",
      "description": "Mutual non-disclosure agreement",
      "usage_count": 45,
      "variables": ["party_a", "party_b", "effective_date"]
    }
  ]
}
```

**Get Template:**
```http
GET /api/templates/{id}/

Response:
{
  "id": "template-uuid-1",
  "name": "Standard NDA Template",
  "content": "This Agreement is made between {{party_a}} and {{party_b}}...",
  "variables": ["party_a", "party_b", "effective_date", "term"],
  "clauses": ["confidentiality", "term", "termination"]
}
```

---

### 9. Clause Library

**Search Clauses:**
```http
GET /api/clauses/?search=liability&category=Liability

Response:
{
  "results": [
    {
      "id": "clause-uuid-1",
      "title": "Limitation of Liability",
      "category": "Liability",
      "content": "Neither party shall be liable...",
      "plain_summary": "Caps damages at contract value",
      "tags": ["liability", "indemnification", "damages"],
      "usage_count": 120
    }
  ]
}
```

**Get Clause:**
```http
GET /api/clauses/{id}/

Response:
{
  "id": "clause-uuid-1",
  "title": "Limitation of Liability",
  "category": "Liability",
  "content": "Full clause text...",
  "plain_summary": "AI-generated summary",
  "variations": [
    {"jurisdiction": "CA", "content": "California-specific version"},
    {"jurisdiction": "NY", "content": "New York-specific version"}
  ]
}
```

---

## Background Tasks

All long-running operations use django-background-tasks for async processing:

### Task Queue Status

Check queue health:
```bash
python manage.py process_tasks --duration=60
```

### Running Background Worker

Start the worker to process tasks:
```bash
# Development (single process)
python manage.py process_tasks

# Production (supervisor/systemd)
python manage.py process_tasks --duration=0 --sleep=5
```

**Task Types:**
1. **Contract Generation**: 30-60s per contract
2. **Embedding Generation**: 5-10s per document
3. **OCR Processing**: 10-30s per page
4. **Email Notifications**: 1-2s per email

---

## Email Notifications

Gmail SMTP notifications sent for:

1. **Contract Generated**: When AI completes generation
2. **Workflow Approval**: When approval is assigned
3. **Workflow Complete**: When all approvals done
4. **SLA Breach Warning**: When deadline approaching

**Configuration:**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'rahuljha996886@gmail.com'
EMAIL_HOST_PASSWORD = '<app-specific-password>'
```

---

## Error Handling

### Common Error Responses

**400 Bad Request:**
```json
{
  "error": "Query parameter is required",
  "field": "query"
}
```

**401 Unauthorized:**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**404 Not Found:**
```json
{
  "detail": "Contract not found."
}
```

**500 Internal Server Error:**
```json
{
  "error": "Gemini API rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

---

## Rate Limits & Quotas

### Gemini API Limits (Free Tier)

- **Embeddings**: 1,500 requests/day
- **Text Generation**: 60 requests/minute
- **Context Window**: 30,000 characters

### Recommendations

1. **Cache embeddings** - Don't regenerate for unchanged content
2. **Batch processing** - Group similar operations
3. **Fallback strategies** - Use keyword search if embeddings fail
4. **Monitor quotas** - Track API usage in logs

---

## Security & Privacy

### PII Protection

All data is redacted before sending to Gemini:

**Redacted:**
- Email addresses → `[EMAIL_1]`
- Phone numbers → `[PHONE_1]`
- SSN → `[SSN_1]`
- Credit cards → `[CARD_1]`

**Restoration:**
After AI processing, original values restored using secure mapping.

### Data Retention

- **Embeddings**: Stored indefinitely for search
- **API Logs**: 90 days
- **Failed Tasks**: 7 days
- **Email Queue**: 24 hours

---

## Testing

Run comprehensive tests:

```bash
# All AI endpoints
python test_ai_endpoints.py

# Specific test
python test_ai_endpoints.py --test=search

# With verbose output
python test_ai_endpoints.py --verbose
```

**Test Coverage:**
- ✅ Authentication
- ✅ PII Redaction
- ✅ Gemini Embeddings
- ✅ Contract Generation
- ✅ Hybrid Search
- ✅ Contract Comparison
- ✅ Related Contracts
- ✅ OCR Processing
- ✅ Clause Summaries
- ✅ Background Tasks

---

## Performance

### Benchmarks

| Operation | Avg Time | P95 | P99 |
|-----------|----------|-----|-----|
| Generate Embedding | 800ms | 1.2s | 2.5s |
| Generate Contract | 15s | 25s | 40s |
| Hybrid Search | 450ms | 850ms | 1.5s |
| Contract Comparison | 8s | 12s | 18s |
| OCR (1 page) | 3s | 5s | 8s |

### Optimization Tips

1. **Pre-generate embeddings** for all contracts on upload
2. **Use hybrid search** with higher keyword weight for speed
3. **Paginate results** - Limit to 20 items max
4. **Cache frequently accessed contracts**
5. **Run background worker** on separate server in production

---

## Deployment

### Environment Variables

```bash
# Required
GEMINI_API_KEY=AIzaSy...
EMAIL_HOST_USER=user@gmail.com
EMAIL_HOST_PASSWORD=app_password
DATABASE_URL=postgresql://...

# Optional
REDIS_URL=redis://localhost:6379/0  # Not required for background_task
TESSERACT_CMD=/usr/bin/tesseract    # OCR binary path
```

### Production Checklist

- [ ] Configure Gemini API key
- [ ] Set up Gmail App Password
- [ ] Run migrations: `python manage.py migrate`
- [ ] Collect static files: `python manage.py collectstatic`
- [ ] Start background worker: `python manage.py process_tasks --duration=0`
- [ ] Configure supervisor/systemd for worker auto-restart
- [ ] Set up monitoring for task queue depth
- [ ] Enable API rate limiting
- [ ] Configure backup for embeddings

---

## Support

For issues or questions:

1. Check logs: `tail -f logs/django.log`
2. Monitor task queue: Check `background_task` table in database
3. Verify API status: `curl http://localhost:8000/api/health/`
4. Review test results: `cat ai_test_results.json`

---

## Changelog

### v1.0.0 (Current)
- ✅ Django-background-tasks integration (removed Celery)
- ✅ Gemini API for embeddings and generation
- ✅ Hybrid search with RRF algorithm
- ✅ PII redaction service
- ✅ Chain-of-Thought contract generation
- ✅ OCR with Tesseract
- ✅ Gmail SMTP notifications
- ✅ Comprehensive test suite

### Upcoming (v1.1.0)
- [ ] WebSocket support for real-time generation progress
- [ ] Multi-language contract support
- [ ] Advanced analytics dashboard
- [ ] Contract version comparison
- [ ] Bulk import/export
- [ ] Google Document AI integration for handwriting

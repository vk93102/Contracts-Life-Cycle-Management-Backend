# AI-Powered CLM System - Complete Feature Documentation

## System Overview

This CLM (Contract Lifecycle Management) system now includes advanced AI-powered features built with Google's Gemini API, providing:

- **AI Contract Generation**: Chain-of-Thought prompting with confidence scoring
- **Hybrid Search**: Keyword + Semantic search with Reciprocal Rank Fusion
- **PII Protection**: Automated redaction before AI processing
- **Contract Analysis**: AI-powered comparison and clause summarization
- **Async Processing**: Celery task queue for long-running operations
- **Real-time Updates**: Email notifications when contracts are ready

---

## Architecture

### Technology Stack

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend Layer                       │
│  React/Vue.js → REST API calls → WebSocket (optional)   │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   Django REST API                        │
│  - JWT Authentication                                    │
│  - Multi-tenant Row-Level Security                      │
│  - ViewSets with DRF                                    │
└─────────────────────────────────────────────────────────┘
                            ↓
┌──────────────┬─────────────────┬───────────────────────┐
│              │                 │                       │
│  PostgreSQL  │   Redis Cache   │   Gemini AI API      │
│  (Supabase)  │   (Celery)      │   (Google Cloud)     │
│              │                 │                       │
│  - Contracts │   - Task Queue  │   - Embeddings       │
│  - Workflows │   - Results     │   - Generation       │
│  - Full-text │                 │   - Analysis         │
└──────────────┴─────────────────┴───────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  Background Workers                      │
│  Celery Workers → Process async tasks → Send emails     │
└─────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. AI Services Layer (`contracts/ai_services.py`)

**GeminiService**
- `generate_embedding(text)` - Creates 768-dim vectors for semantic search
- `generate_contract_with_cot(...)` - Chain-of-Thought contract generation
- `generate_clause_summary(clause)` - Plain-English explanations
- `compare_contracts(a, b)` - AI-powered diff analysis

**PIIRedactionService**
- `redact_pii(text)` - Remove sensitive data before AI processing
- `restore_pii(text, map)` - Re-insert PII after processing

**Features:**
- Retry logic with exponential backoff
- Text truncation to API limits
- Prompt provenance tracking (SHA256 hashing)
- Confidence scoring (1-10 scale)

#### 2. Search Services Layer (`contracts/search_services.py`)

**HybridSearchService**
- `search_contracts(...)` - Multi-modal search
  - **Keyword Mode**: PostgreSQL full-text search (tsvector)
  - **Semantic Mode**: Vector similarity with cosine distance
  - **Hybrid Mode**: Reciprocal Rank Fusion (RRF)
  
- `find_similar_contracts(...)` - Nearest neighbor search
- `get_search_suggestions(...)` - Autocomplete functionality

**Reciprocal Rank Fusion Algorithm:**
```python
# For each document
RRF_score = Σ (1 / (k + rank))

# Where:
# k = 60 (constant)
# rank = position in search results (1-indexed)
# Σ = sum across keyword and semantic rankings
```

#### 3. Async Task Processing (`contracts/tasks.py`)

**Celery Tasks:**
- `generate_contract_async` - Background contract generation
- `generate_embeddings_for_contract` - Vector embedding creation
- `send_contract_ready_notification` - Email notifications
- `process_ocr_document` - OCR processing (requires setup)

**Task Features:**
- Max 3 retries with exponential backoff
- 30-minute timeout per task
- Result persistence in Redis
- Error tracking in contract metadata

#### 4. API Endpoints (`contracts/ai_views.py`)

**SearchViewSet**
- `POST /api/search/global/` - Global hybrid search
- `GET /api/search/suggestions/` - Autocomplete

**AIAnalysisViewSet**
- `POST /api/analysis/compare/` - Compare contracts
- `GET /api/contracts/{id}/related/` - Find similar contracts
- `POST /api/analysis/clause-summary/` - Summarize clause

**AsyncContractGenerationViewSet**
- `POST /api/generation/start/` - Start async generation (202 Accepted)
- `GET /api/generation/{id}/status/` - Check generation status

**DocumentProcessingViewSet**
- `POST /api/documents/{id}/reprocess/` - Trigger OCR
- `GET /api/documents/{id}/ocr-status/` - Check OCR status
- `GET /api/documents/{id}/extracted-text/` - Get OCR results

---

## API Endpoint Reference

### 1. Hybrid Search

**Endpoint:** `POST /api/search/global/`

**Request:**
```json
{
  "query": "employment agreement",
  "mode": "hybrid",
  "filters": {
    "status": "active",
    "date_gte": "2024-01-01",
    "contract_type": "MSA",
    "value_gte": 10000
  },
  "limit": 10
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "uuid",
      "title": "Employment Agreement - John Doe",
      "score": 0.92,
      "match_type": "hybrid",
      "contract": {
        "id": "uuid",
        "title": "Employment Agreement - John Doe",
        "contract_type": "Employment",
        "status": "active",
        "created_at": "2024-01-15T10:00:00Z",
        "description": "Full-time employment contract..."
      }
    }
  ],
  "total": 25,
  "mode": "hybrid",
  "query": "employment agreement"
}
```

**Search Modes:**
- `keyword` - Traditional PostgreSQL full-text search
- `semantic` - Vector similarity search using Gemini embeddings
- `hybrid` - Combined using Reciprocal Rank Fusion

---

### 2. Autocomplete Suggestions

**Endpoint:** `GET /api/search/suggestions/?q=emp&limit=5`

**Response:**
```json
{
  "suggestions": [
    "Employment Agreement",
    "Employee NDA",
    "Employment Contract Template"
  ]
}
```

---

### 3. Async Contract Generation

**Endpoint:** `POST /api/generation/start/`

**Request:**
```json
{
  "title": "Service Agreement - Acme Corp",
  "contract_type": "MSA",
  "description": "Master Service Agreement",
  "variables": {
    "party_a": "Acme Corporation",
    "party_b": "Client Industries Inc.",
    "party_a_email": "legal@acme.com",
    "term": "24 months",
    "payment_terms": "Net 30",
    "total_value": "$150,000",
    "services": "Software development"
  },
  "special_instructions": "Include termination with 60-day notice. Add liability cap."
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "celery-task-uuid",
  "contract_id": "contract-uuid",
  "status": "processing",
  "message": "Contract generation started. You will be notified when ready."
}
```

**Check Status:** `GET /api/generation/{contract_id}/status/`

**Response (Completed):**
```json
{
  "contract_id": "uuid",
  "status": "completed",
  "task_id": "celery-task-uuid",
  "confidence_score": 8,
  "generated_text": "MASTER SERVICE AGREEMENT\n\nThis Agreement..."
}
```

**Generation Process:**
1. PII redaction (emails, names, etc.)
2. Chain-of-Thought prompting:
   - Step 1: Generate outline
   - Step 2: Generate full contract
   - Step 3: Self-validate and score
3. PII restoration
4. Rule-based validation
5. Embedding generation
6. Email notification

---

### 4. Clause Summarization

**Endpoint:** `POST /api/analysis/clause-summary/`

**Request:**
```json
{
  "clause_text": "Party A hereby indemnifies and holds harmless Party B from any and all claims, damages, liabilities, costs, and expenses arising out of the performance of services."
}
```

**Response:**
```json
{
  "original_text": "Party A hereby indemnifies...",
  "summary": "This means Party A agrees to protect Party B from legal claims and cover any costs if someone sues Party B because of Party A's work under this agreement. Essentially, Party A takes responsibility for legal issues arising from their services."
}
```

---

### 5. Contract Comparison

**Endpoint:** `POST /api/analysis/compare/`

**Request:**
```json
{
  "contract_a_id": "uuid-1",
  "contract_b_id": "uuid-2"
}
```

**Response:**
```json
{
  "contract_a": {
    "id": "uuid-1",
    "title": "Service Agreement v1"
  },
  "contract_b": {
    "id": "uuid-2",
    "title": "Service Agreement v2"
  },
  "comparison": {
    "summary": "Contract B includes additional liability protections and extends the payment terms from Net 30 to Net 45 days.",
    "key_differences": [
      "Payment terms: 30 days → 45 days",
      "Liability cap added: $1M",
      "Termination notice: 30 days → 60 days"
    ],
    "risk_assessment": "MEDIUM - Extended payment terms may impact cash flow",
    "recommendation": "Consider negotiating payment terms back to Net 30"
  }
}
```

---

### 6. Related Contracts

**Endpoint:** `GET /api/contracts/{id}/related/?limit=5`

**Response:**
```json
{
  "source_contract": {
    "id": "uuid",
    "title": "Employment Agreement - John Doe"
  },
  "related": [
    {
      "id": "related-uuid-1",
      "similarity_score": 0.94,
      "contract": {
        "id": "related-uuid-1",
        "title": "Employment Agreement - Jane Smith",
        "contract_type": "Employment",
        "status": "active"
      }
    },
    {
      "id": "related-uuid-2",
      "similarity_score": 0.87,
      "contract": {
        "id": "related-uuid-2",
        "title": "Contractor Agreement - Bob Johnson",
        "contract_type": "Consulting",
        "status": "active"
      }
    }
  ]
}
```

---

### 7. OCR Processing

**Trigger Reprocessing:** `POST /api/documents/{id}/reprocess/`

**Response:**
```json
{
  "status": "processing",
  "task_id": "celery-task-uuid",
  "message": "OCR processing started"
}
```

**Check Status:** `GET /api/documents/{id}/ocr-status/`

**Response:**
```json
{
  "status": "completed",
  "task_id": "celery-task-uuid",
  "message": "OCR status: completed"
}
```

**Get Extracted Text:** `GET /api/documents/{id}/extracted-text/`

**Response:**
```json
{
  "text": "EMPLOYMENT AGREEMENT\n\nThis Agreement...",
  "confidence": 0.95,
  "word_count": 1234
}
```

---

## Data Models

### Contract Model (Extended)

```python
class Contract(models.Model):
    # ... existing fields ...
    
    metadata = models.JSONField(default=dict, blank=True)
    # Stores:
    # - embedding: [0.123, -0.456, ...] (768 dimensions)
    # - generation_status: "queued|processing|completed|failed"
    # - generation_task_id: Celery task UUID
    # - generated_text: AI-generated contract text
    # - generation_metadata:
    #     - model_version: "gemini-pro"
    #     - confidence_score: 8 (1-10)
    #     - prompt_id: SHA256 hash
    #     - timestamp: ISO 8601
    # - validation_result:
    #     - is_valid: true/false
    #     - errors: []
    #     - warnings: []
    # - ocr_status: "not_started|processing|completed|failed"
    # - ocr_text: Extracted text
    # - ocr_confidence: 0-1
```

---

## Configuration Guide

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/clmdb

# Cloudflare R2
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_ACCOUNT_ID=xxx
R2_BUCKET_NAME=clm

# Gemini AI
GEMINI_API_KEY=AIzaSyBhDptUGKf0q3g5KmkU9ghntXWdF_49_mA

# Redis (Celery)
REDIS_URL=redis://localhost:6379/0

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@clm-system.com

# Django
DJANGO_SECRET_KEY=your-secret-key
DEBUG=False
```

### Django Settings (settings.py)

```python
# Celery
CELERY_BROKER_URL = os.getenv('REDIS_URL')
CELERY_RESULT_BACKEND = os.getenv('REDIS_URL')
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes

# Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Email
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND')
EMAIL_HOST = os.getenv('EMAIL_HOST')
# ... etc
```

---

## Running the System

### Local Development

```bash
# Terminal 1: Redis
brew services start redis

# Terminal 2: Celery Worker
celery -A clm_backend worker --loglevel=info

# Terminal 3: Django Server
python manage.py runserver 4000
```

### Production (Render.com)

**render.yaml:**
```yaml
services:
  # Web Service
  - type: web
    name: clm-backend
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "gunicorn clm_backend.wsgi:application"
    envVars:
      - key: GEMINI_API_KEY
        value: AIzaSyBhDptUGKf0q3g5KmkU9ghntXWdF_49_mA
      - key: REDIS_URL
        fromService:
          name: clm-redis
          type: redis
          property: connectionString

  # Celery Worker
  - type: worker
    name: clm-celery-worker
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "celery -A clm_backend worker --loglevel=info --concurrency=2"
    envVars:
      - key: REDIS_URL
        fromService:
          name: clm-redis
          type: redis
          property: connectionString

databases:
  - name: clm-redis
    type: redis
    plan: free
```

---

## Performance Considerations

### Embedding Generation
- **Time:** 1-2 seconds per contract
- **Dimensions:** 768 floats = ~3KB storage
- **Recommendation:** Generate async in background

### Contract Generation
- **Time:** 30-60 seconds (Chain-of-Thought requires 3 API calls)
- **Recommendation:** Always use async endpoint with Celery

### Search Performance
- **Keyword Search:** <100ms
- **Semantic Search:** <500ms (with pre-computed embeddings)
- **Hybrid Search:** <700ms (runs both in parallel)

### Caching Strategy
```python
# Cache search results for 5 minutes
from django.core.cache import cache

cache_key = f"search:{query}:{mode}"
results = cache.get(cache_key)

if not results:
    results = hybrid_search_service.search_contracts(...)
    cache.set(cache_key, results, 300)  # 5 min
```

---

## Security Considerations

### PII Protection
- All user data is redacted before sending to Gemini API
- Token replacement: `john.doe@example.com` → `[EMAIL_1]`
- Original PII restored after AI processing
- Redaction map never sent to external services

### API Key Security
- Store Gemini API key in environment variables
- Never commit to version control
- Rotate keys regularly
- Use separate keys for dev/staging/production

### Multi-Tenancy
- All queries filtered by `tenant_id`
- Row-level security enforced
- Embeddings isolated per tenant

---

## Monitoring & Debugging

### Celery Task Monitoring
```bash
# Check task status
celery -A clm_backend inspect active

# Check registered tasks
celery -A clm_backend inspect registered

# Purge failed tasks
celery -A clm_backend purge
```

### Logging
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Contract generation started")
logger.error("Gemini API error", exc_info=True)
```

### Debugging Failed Generations
```python
# Get contract metadata
contract = Contract.objects.get(id='uuid')
print(contract.metadata)

# Check:
# - generation_status: "failed"
# - generation_error: Error message
# - generation_task_id: Celery task ID
```

---

## Future Enhancements

### 1. WebSocket Support
Real-time updates during contract generation:
```javascript
const ws = new WebSocket('ws://localhost:4000/ws/contracts/uuid/');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Generation progress: ${data.progress}%`);
};
```

### 2. OCR Integration
Complete OCR setup with Tesseract or AWS Textract for document uploads.

### 3. Template Library
Pre-built contract templates with AI-generated clause variations.

### 4. Compliance Checking
AI-powered compliance validation against regulations (GDPR, CCPA, etc.).

### 5. Batch Processing
Process multiple contracts in parallel with bulk embeddings generation.

---

## Troubleshooting

### Issue: "Celery worker not processing tasks"
**Solution:**
```bash
# Check Redis connection
redis-cli ping

# Restart Celery with verbose logging
celery -A clm_backend worker --loglevel=debug

# Check for errors in output
```

### Issue: "Gemini API quota exceeded"
**Solution:**
- Check API quotas: https://console.cloud.google.com/apis/
- Implement rate limiting
- Cache results when possible

### Issue: "Embeddings not generating"
**Solution:**
```python
# Test Gemini API directly
from contracts.ai_services import gemini_service

embedding = gemini_service.generate_embedding("test text")
print(f"Embedding dimensions: {len(embedding)}")
```

---

## Support & Resources

- **Gemini API Docs:** https://ai.google.dev/docs
- **Celery Docs:** https://docs.celeryproject.org/
- **Django Channels (WebSockets):** https://channels.readthedocs.io/
- **PostgreSQL Full-Text Search:** https://www.postgresql.org/docs/current/textsearch.html

---

**Version:** 2.0.0 (AI-Powered)  
**Last Updated:** January 2024  
**Author:** CLM Development Team

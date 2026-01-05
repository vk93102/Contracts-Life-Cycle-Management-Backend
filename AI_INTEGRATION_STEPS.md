# AI Integration Steps for CLM Backend

This document provides step-by-step instructions for integrating AI-powered features into the CLM system.

## Table of Contents
1. [Install Dependencies](#1-install-dependencies)
2. [Configure Environment Variables](#2-configure-environment-variables)
3. [Set Up Redis (Async Tasks)](#3-set-up-redis)
4. [Configure Email Backend](#4-configure-email-backend)
5. [Run Database Migrations](#5-run-database-migrations)
6. [Start Celery Worker](#6-start-celery-worker)
7. [Test AI Endpoints](#7-test-ai-endpoints)
8. [Optional: OCR Integration](#8-optional-ocr-integration)
9. [Optional: WebSocket Support](#9-optional-websocket-support)

---

## 1. Install Dependencies

**Time Required:** 3-4 minutes

### Step 1.1: Install Python Packages

```bash
cd /Users/vishaljha/Desktop/SK/CLM/backend
pip install -r requirements.txt
```

**New packages being installed:**
- `google-generativeai==0.3.2` - Gemini AI SDK
- `numpy==1.24.3` - Vector operations for search
- `celery==5.3.6` - Async task processing
- `redis==5.0.1` - Message broker for Celery

**Expected Output:**
```
Successfully installed google-generativeai-0.3.2 numpy-1.24.3 celery-5.3.6 redis-5.0.1
```

### Step 1.2: Verify Installation

```bash
python -c "import google.generativeai as genai; import numpy; import celery; print('✅ All packages installed')"
```

---

## 2. Configure Environment Variables

**Time Required:** 2 minutes

Your `.env` file already contains the Gemini API key. Let's verify and add additional settings:

### Step 2.1: Verify Gemini API Key

```bash
grep GEMINI_API_KEY .env
```

**Expected Output:**
```
GEMINI_API_KEY=AIzaSyBhDptUGKf0q3g5KmkU9ghntXWdF_49_mA
```

✅ **Already configured!**

### Step 2.2: Add Redis URL (for Celery)

Add to your `.env` file:

```bash
# Redis Configuration (for async tasks)
REDIS_URL=redis://localhost:6379/0
```

**For Production (Render.com):**
Render provides Redis add-ons. Update `.env` with:
```
REDIS_URL=redis://red-xxxxx:6379/0  # Render will provide this
```

### Step 2.3: Configure Email (Optional but Recommended)

Add to `.env` for Gmail SMTP:

```bash
# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password  # Use App Password, not regular password
DEFAULT_FROM_EMAIL=noreply@clm-system.com
```

**For Development (Console):**
```bash
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```
This will print emails to console instead of sending.

---

## 3. Set Up Redis

**Time Required:** 3-5 minutes

### Option A: Local Development (macOS)

```bash
# Install Redis via Homebrew
brew install redis

# Start Redis server
brew services start redis

# Verify Redis is running
redis-cli ping
# Expected: PONG
```

### Option B: Docker (All platforms)

```bash
docker run -d -p 6379:6379 --name clm-redis redis:7-alpine
```

### Option C: Production (Render.com)

1. Go to Render Dashboard
2. Click "New +" → "Redis"
3. Name: `clm-redis`
4. Plan: Free (256 MB)
5. Copy the **Internal Redis URL**
6. Add to environment variables in Render

**No manual setup required - wait 2-3 minutes for provisioning**

---

## 4. Configure Email Backend

**Time Required:** 2 minutes (if using Gmail)

### Step 4.1: Create Gmail App Password

1. Go to Google Account → Security
2. Enable 2-Factor Authentication
3. Search "App passwords"
4. Create new app password for "Mail"
5. Copy the 16-character password

### Step 4.2: Update .env

```bash
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=abcd efgh ijkl mnop  # App password from Step 4.1
```

### Step 4.3: Test Email (Optional)

```bash
python manage.py shell
```

In Django shell:
```python
from django.core.mail import send_mail

send_mail(
    'Test Email',
    'This is a test from CLM system',
    'noreply@clm-system.com',
    ['your-email@gmail.com'],
    fail_silently=False,
)
# Expected: 1 (email sent successfully)
```

---

## 5. Run Database Migrations

**Time Required:** 1 minute

No new migrations needed for AI features (we use existing `metadata` JSON field).

**Verify database is ready:**

```bash
python manage.py migrate --check
```

**Expected Output:**
```
System check identified no issues (0 silenced).
```

---

## 6. Start Celery Worker

**Time Required:** Ongoing (background process)

### Step 6.1: Start Celery in New Terminal

Open a new terminal window and run:

```bash
cd /Users/vishaljha/Desktop/SK/CLM/backend
celery -A clm_backend worker --loglevel=info
```

**Expected Output:**
```
 -------------- celery@YourMac v5.3.6 (emerald-rush)
 ---- **** ----- 
 --- * ***  * -- Darwin-23.0.0-arm64-arm-64bit
 -- * - **** --- 
 - ** ---------- [config]
 - ** ---------- .> app:         clm_backend:0x10a6c3d90
 - ** ---------- .> transport:   redis://localhost:6379/0
 - ** ---------- .> results:     redis://localhost:6379/0
 - *** --- * --- .> concurrency: 8 (prefork)
 -- ******* ---- .> task events: OFF
 --- ***** ----- 
 -------------- [queues]
                .> celery           exchange=celery(direct) key=celery
                

[tasks]
  . contracts.tasks.generate_contract_async
  . contracts.tasks.generate_embeddings_for_contract
  . contracts.tasks.send_contract_ready_notification
  . contracts.tasks.process_ocr_document

[2024-01-03 12:00:00,000: INFO/MainProcess] Connected to redis://localhost:6379/0
[2024-01-03 12:00:00,000: INFO/MainProcess] celery ready.
```

✅ **Celery is ready to process async tasks!**

### Step 6.2: Keep Celery Running

**Important:** Keep this terminal window open. Celery needs to run in the background to process async contract generation.

**For Production:**
Use process managers like:
- Supervisor
- systemd
- Render's background workers

---

## 7. Test AI Endpoints

**Time Required:** 5 minutes

### Step 7.1: Start Django Server

In another terminal:

```bash
python manage.py runserver 4000
```

### Step 7.2: Get Authentication Token

```bash
curl -X POST http://localhost:4000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }'
```

**Save the access token from response.**

### Step 7.3: Test Hybrid Search

```bash
TOKEN="your-access-token-here"

curl -X POST http://localhost:4000/api/search/global/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "employment agreement",
    "mode": "hybrid",
    "limit": 5
  }'
```

**Expected Response:**
```json
{
  "results": [
    {
      "id": "...",
      "title": "Employment Agreement",
      "score": 0.92,
      "match_type": "hybrid",
      "contract": {
        "id": "...",
        "title": "Employment Agreement",
        "contract_type": "MSA",
        "status": "active"
      }
    }
  ],
  "total": 5,
  "mode": "hybrid",
  "query": "employment agreement"
}
```

### Step 7.4: Test Async Contract Generation

```bash
curl -X POST http://localhost:4000/api/generation/start/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Service Agreement",
    "contract_type": "MSA",
    "description": "Master Service Agreement",
    "variables": {
      "party_a": "Acme Corp",
      "party_b": "Client Inc",
      "term": "12 months",
      "payment_terms": "Net 30"
    },
    "special_instructions": "Include termination clause with 30-day notice"
  }'
```

**Expected Response (202 Accepted):**
```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "contract_id": "contract-uuid-here",
  "status": "processing",
  "message": "Contract generation started. You will be notified when ready."
}
```

**⏱️ Wait 30-60 seconds for generation to complete.**

### Step 7.5: Check Generation Status

```bash
CONTRACT_ID="contract-uuid-from-previous-response"

curl -X GET http://localhost:4000/api/generation/$CONTRACT_ID/status/ \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response:**
```json
{
  "contract_id": "...",
  "status": "completed",
  "task_id": "...",
  "confidence_score": 8,
  "generated_text": "MASTER SERVICE AGREEMENT\n\nThis Agreement..."
}
```

### Step 7.6: Test Contract Comparison

```bash
curl -X POST http://localhost:4000/api/analysis/compare/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "contract_a_id": "contract-uuid-1",
    "contract_b_id": "contract-uuid-2"
  }'
```

### Step 7.7: Test Related Contracts

```bash
curl -X GET http://localhost:4000/api/contracts/$CONTRACT_ID/related/?limit=5 \
  -H "Authorization: Bearer $TOKEN"
```

### Step 7.8: Test Clause Summary

```bash
curl -X POST http://localhost:4000/api/analysis/clause-summary/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clause_text": "Party A hereby indemnifies and holds harmless Party B from any and all claims, damages, liabilities, costs, and expenses arising out of or related to the performance of services under this Agreement."
  }'
```

**Expected Response:**
```json
{
  "original_text": "Party A hereby indemnifies...",
  "summary": "This means Party A agrees to protect Party B from legal claims and cover any costs if someone sues Party B because of Party A's work under this agreement."
}
```

---

## 8. Optional: OCR Integration

**Time Required:** 10-15 minutes (if implementing)

### Option A: Tesseract OCR (Free, Open Source)

```bash
# Install Tesseract
brew install tesseract

# Install Python wrapper
pip install pytesseract

# Test installation
tesseract --version
```

**Update contracts/tasks.py:**
```python
import pytesseract
from PIL import Image

@shared_task
def process_ocr_document(document_id: str):
    # Download from R2
    # ...
    
    # Run OCR
    text = pytesseract.image_to_string(Image.open(file_path))
    
    # Store results
    contract.metadata['ocr_text'] = text
    contract.save()
```

### Option B: AWS Textract (Advanced, Paid)

```bash
pip install boto3
```

**Configure AWS credentials in .env:**
```
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_TEXTRACT_REGION=us-east-1
```

### Option C: Google Document AI

Uses the same Gemini API key. See: https://cloud.google.com/document-ai

---

## 9. Optional: WebSocket Support

**Time Required:** 15-20 minutes

For real-time contract generation updates, implement Django Channels:

```bash
pip install channels channels-redis daphne
```

**Update settings.py:**
```python
INSTALLED_APPS += ['channels']

ASGI_APPLICATION = 'clm_backend.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [os.getenv('REDIS_URL', 'redis://localhost:6379/0')],
        },
    },
}
```

**Create consumers.py:**
```python
from channels.generic.websocket import AsyncWebsocketConsumer
import json

class ContractGenerationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.contract_id = self.scope['url_route']['kwargs']['contract_id']
        await self.channel_layer.group_add(
            f'contract_{self.contract_id}',
            self.channel_name
        )
        await self.accept()
    
    async def contract_update(self, event):
        await self.send(text_data=json.dumps(event['data']))
```

---

## Summary of Integration Steps

### ✅ Completed Automatically
- AI service modules created
- Hybrid search implemented
- URL routing configured
- Celery tasks defined
- Requirements.txt updated

### 🔧 Manual Setup Required

1. **Install Dependencies** (3-4 min)
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Redis** (1-2 min)
   ```bash
   brew install redis
   brew services start redis
   ```

3. **Start Celery Worker** (1 min, keep running)
   ```bash
   celery -A clm_backend worker --loglevel=info
   ```

4. **Configure Email** (2 min, optional)
   - Add Gmail App Password to .env
   - Or use console backend for development

5. **Test Endpoints** (5 min)
   - Use provided curl commands
   - Verify async generation works

---

## Production Deployment Checklist

### Render.com Deployment

1. **Add Redis Add-on**
   - Dashboard → New → Redis
   - Copy Internal Redis URL
   - Add to environment variables

2. **Add Worker Service**
   - Dashboard → New → Background Worker
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `celery -A clm_backend worker --loglevel=info --concurrency=2`

3. **Environment Variables**
   ```
   GEMINI_API_KEY=AIzaSyBhDptUGKf0q3g5KmkU9ghntXWdF_49_mA
   REDIS_URL=redis://red-xxxxx:6379/0
   EMAIL_HOST_USER=your-email@gmail.com
   EMAIL_HOST_PASSWORD=your-app-password
   ```

4. **Update render.yaml**
   ```yaml
   services:
     - type: web
       name: clm-backend
       # ... existing config ...
   
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

## Troubleshooting

### Issue: Celery worker not starting

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Check Python path
which python

# Use full path to celery
python -m celery -A clm_backend worker --loglevel=info
```

### Issue: Gemini API errors

**Solution:**
```bash
# Verify API key
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('GEMINI_API_KEY'))"

# Test API directly
python -c "import google.generativeai as genai; genai.configure(api_key='YOUR_KEY'); print(genai.list_models())"
```

### Issue: Email not sending

**Solution:**
- Use console backend for development
- Check Gmail App Password (not regular password)
- Verify 2FA is enabled on Google Account

---

## Next Steps

1. ✅ Install dependencies
2. ✅ Start Redis
3. ✅ Start Celery worker
4. ✅ Test async generation
5. ⏭️ Deploy to production
6. ⏭️ Implement OCR (optional)
7. ⏭️ Add WebSocket support (optional)

**Estimated Total Setup Time:** 10-15 minutes

All AI features are now ready to use! 🚀

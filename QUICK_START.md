# 🚀 Quick Start Guide - AI-Powered CLM System

## ⚡ 3-Minute Setup (Local Development)

### Step 1: Install Dependencies (1 min)
```bash
cd /Users/vishaljha/Desktop/SK/CLM/backend
pip install -r requirements.txt
```

### Step 2: Start Redis (1 min)
```bash
brew install redis
brew services start redis
```

### Step 3: Start Celery Worker (keep running)
```bash
celery -A clm_backend worker --loglevel=info
```

### Step 4: Start Django Server (in new terminal)
```bash
python manage.py runserver 4000
```

---

## 🧪 Quick Test (1 minute)

```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:4000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access'])")

# Test hybrid search
curl -X POST http://localhost:4000/api/search/global/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"agreement","mode":"hybrid","limit":5}'

# Start async contract generation
curl -X POST http://localhost:4000/api/generation/start/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title":"Test Agreement",
    "contract_type":"MSA",
    "variables":{"party_a":"Acme","party_b":"Client","term":"12 months"}
  }'
```

---

## 📚 Key Endpoints

### Hybrid Search
```bash
POST /api/search/global/
{
  "query": "employment agreement",
  "mode": "hybrid",  # or "keyword", "semantic"
  "limit": 10
}
```

### Async Contract Generation
```bash
POST /api/generation/start/
{
  "title": "Service Agreement",
  "contract_type": "MSA",
  "variables": {"party_a": "...", "party_b": "..."},
  "special_instructions": "Include termination clause"
}
```

### Contract Comparison
```bash
POST /api/analysis/compare/
{
  "contract_a_id": "uuid1",
  "contract_b_id": "uuid2"
}
```

### Clause Summary
```bash
POST /api/analysis/clause-summary/
{
  "clause_text": "Party A hereby indemnifies..."
}
```

### Related Contracts
```bash
GET /api/contracts/{id}/related/?limit=5
```

---

## 🎯 What's New (AI Features)

✅ **Hybrid Search** - Keyword + Semantic + RRF fusion  
✅ **AI Generation** - Chain-of-Thought with confidence scoring  
✅ **PII Protection** - Auto redaction before AI processing  
✅ **Async Processing** - 30-60s generations in background  
✅ **Email Notifications** - "Contract Ready" alerts  
✅ **Clause Summaries** - Plain-English explanations  
✅ **Contract Comparison** - AI-powered diff analysis  
✅ **Related Contracts** - Semantic similarity search  

---

## 📖 Documentation

- **Setup Guide:** `AI_INTEGRATION_STEPS.md`
- **API Reference:** `AI_FEATURES_DOCUMENTATION.md`
- **Summary:** `AI_IMPLEMENTATION_SUMMARY.md`

---

## 🔧 Troubleshooting

### Celery not starting?
```bash
redis-cli ping  # Should return PONG
python -m celery -A clm_backend worker --loglevel=debug
```

### Gemini API errors?
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('GEMINI_API_KEY'))"
```

### Email not working?
- For dev: Use `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`
- For prod: Get Gmail App Password (requires 2FA)

---

## 🚢 Production Deployment (Render.com)

1. **Add Redis:**
   - Dashboard → New → Redis → Free plan

2. **Add Celery Worker:**
   - Dashboard → New → Background Worker
   - Start command: `celery -A clm_backend worker --loglevel=info --concurrency=2`

3. **Environment Variables:**
   ```
   GEMINI_API_KEY=AIzaSyBhDptUGKf0q3g5KmkU9ghntXWdF_49_mA
   REDIS_URL=redis://red-xxxxx:6379/0
   ```

4. **Deploy:**
   ```bash
   git add .
   git commit -m "Add AI features"
   git push
   ```

---

## 📞 Support

- **Gemini API:** https://ai.google.dev/docs
- **Celery:** https://docs.celeryproject.org/
- **Django Channels (WebSockets):** https://channels.readthedocs.io/

---

**Version:** 2.0.0 (AI-Powered)  
**Last Updated:** January 2024

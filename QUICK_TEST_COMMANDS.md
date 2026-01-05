# ✅ COMPLETE TESTING GUIDE - Week 1, 2, 3 All Endpoints

## 🚀 Quick Start (1 Command)

```bash
# In backend directory
cd /Users/vishaljha/Desktop/SK/CLM/backend

# Make sure server is running (if not, start in another terminal first)
python manage.py runserver 4000

# Run all tests automatically
./run_all_api_tests.sh
```

**This runs 11 endpoints automatically and shows you REAL data.**

---

## 📋 Manual Testing (If you prefer step-by-step)

### Step 1: Start Backend Services

**Terminal 1 - Django Server:**
```bash
cd /Users/vishaljha/Desktop/SK/CLM/backend
python manage.py runserver 4000
```

Output should show:
```
Starting development server at http://127.0.0.1:4000/
Django version 5.0, using settings 'clm_backend.settings'
Quit the server with CONTROL-C.
```

**Terminal 2 - Background Worker (Optional but Recommended):**
```bash
cd /Users/vishaljha/Desktop/SK/CLM/backend
python manage.py process_tasks
```

Output should show:
```
Running the background task scheduler
Processing tasks...
```

### Step 2: Copy-Paste Curl Commands

**Terminal 3 - Run Tests:**

Use the curl commands below in sequence. Copy entire block and paste.

---

## 🔑 WEEK 1: Authentication & Contract Management

### 1️⃣ Login - Get JWT Token

**Copy and paste this entire block:**
```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:4000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123"
  }' | python3 -c "import sys, json; print(json.load(sys.stdin)['access'])")

# Verify token
echo "Token received: ${TOKEN:0:50}..."
```

**Expected Output:**
```
Token received: eyJ0eXAiOiJKV1QiLCJhbGc...
```

---

### 2️⃣ List All Contracts

```bash
curl -X GET http://localhost:4000/api/contracts/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" | python3 -m json.tool | head -50
```

**Expected Output:**
```json
{
  "count": 33,
  "next": "http://localhost:4000/api/contracts/?page=2",
  "previous": null,
  "results": [
    {
      "id": "3f11a152-be06-43b3-9df2-dfc9ab172644",
      "title": "Software Development MSA",
      "contract_type": "MSA",
      "status": "active",
      "value": 250000
    },
    ...
  ]
}
```

**✓ You now have 33 contracts to work with**

---

### 3️⃣ Get Specific Contract

```bash
# Get first contract ID
CONTRACT_ID=$(curl -s -X GET http://localhost:4000/api/contracts/ \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin)['results'][0]['id'])")

echo "Using contract: $CONTRACT_ID"

# Get full details
curl -X GET http://localhost:4000/api/contracts/$CONTRACT_ID/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -60
```

**Expected Output:**
```json
{
  "id": "3f11a152-be06-43b3-9df2-dfc9ab172644",
  "title": "Software Development MSA",
  "metadata": {
    "parties": ["Acme Corp", "Client Inc"],
    "value": 250000,
    "embedding": [0.023, 0.145, -0.087, ...]  // 768 dimensions
  },
  "content": "MASTER SERVICE AGREEMENT\n\nThis Agreement made and entered...",
  ...
}
```

**✓ Contract has embedding vector for AI search**

---

## 🤖 WEEK 2: AI Features & Advanced Search

### 4️⃣ Hybrid Search

```bash
curl -X POST http://localhost:4000/api/search/global/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "software development intellectual property",
    "mode": "hybrid",
    "limit": 5
  }' | python3 -m json.tool
```

**Expected Output:**
```json
{
  "results": [
    {
      "id": "3f11a152-be06-43b3-9df2-dfc9ab172644",
      "title": "Software Development MSA",
      "score": 0.892,
      "match_type": "hybrid_rrf"
    },
    {
      "id": "contract-uuid-2",
      "title": "Consulting Services SOW",
      "score": 0.756,
      "match_type": "semantic"
    }
  ],
  "total": 15,
  "execution_time_ms": 450
}
```

**✓ Search returns REAL contracts with scores (not 0 results!)**

---

### 5️⃣ Autocomplete

```bash
curl -X GET "http://localhost:4000/api/search/suggestions/?q=soft&limit=5" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected Output:**
```json
{
  "suggestions": [
    {
      "id": "3f11a152-be06-43b3-9df2-dfc9ab172644",
      "title": "Software Development Master Service Agreement",
      "contract_type": "MSA"
    },
    {
      "id": "contract-uuid-3",
      "title": "Employment Agreement - Senior Software Engineer",
      "contract_type": "Employment"
    }
  ]
}
```

**✓ Real titles suggested, not empty**

---

### 6️⃣ Clause Summary - AI Plain English

```bash
curl -X POST http://localhost:4000/api/analysis/clause-summary/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clause_text": "The Disclosing Party shall not be liable for any indirect, incidental, special, consequential or punitive damages, or any loss of profits or revenues."
  }' | python3 -m json.tool
```

**Expected Output:**
```json
{
  "original_text": "The Disclosing Party shall not be liable...",
  "plain_summary": "This clause limits the company's liability. They won't 
                   be responsible for indirect damages like lost profits 
                   or business interruption, even if they caused the problem. 
                   You can only recover direct damages.",
  "key_points": [
    "Limits liability to direct damages only",
    "Excludes lost profits and business interruption",
    "Applies regardless of fault"
  ],
  "confidence": 0.92
}
```

**✓ REAL Gemini response (not template text)**

---

### 7️⃣ Related Contracts

```bash
curl -X GET "http://localhost:4000/api/contracts/$CONTRACT_ID/related/?limit=5" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Expected Output:**
```json
{
  "source_contract": {
    "id": "3f11a152-be06-43b3-9df2-dfc9ab172644",
    "title": "Software Development MSA"
  },
  "related_contracts": [
    {
      "contract": {
        "id": "contract-uuid-4",
        "title": "SaaS Subscription Agreement",
        "contract_type": "Subscription"
      },
      "similarity_score": 0.789
    },
    {
      "contract": {
        "id": "contract-uuid-5",
        "title": "Consulting Services SOW",
        "contract_type": "SOW"
      },
      "similarity_score": 0.756
    }
  ]
}
```

**✓ Semantic similarity working (0.78-0.79 match)**

---

### 8️⃣ Contract Comparison - AI Analysis

```bash
# Get second contract for comparison
CONTRACT_ID_2=$(curl -s -X GET http://localhost:4000/api/contracts/ \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin)['results'][1]['id'])")

# Compare contracts
curl -X POST http://localhost:4000/api/analysis/compare/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"contract_a_id\": \"$CONTRACT_ID\",
    \"contract_b_id\": \"$CONTRACT_ID_2\"
  }" | python3 -m json.tool | head -100
```

**Expected Output:**
```json
{
  "summary": "Contract A provides stronger intellectual property protection 
             while Contract B offers more flexibility...",
  "key_differences": [
    {
      "aspect": "IP Ownership",
      "contract_a": "All work product owned by client",
      "contract_b": "Vendor retains ownership",
      "significance": "high"
    },
    {
      "aspect": "Termination Notice",
      "contract_a": "90-day notice",
      "contract_b": "30-day notice",
      "significance": "medium"
    }
  ],
  "risk_analysis": {
    "contract_a_advantages": [
      "Better IP protection",
      "Longer termination notice"
    ],
    "contract_b_advantages": [
      "More flexibility"
    ]
  },
  "recommendations": "Contract A is better for owning technology assets..."
}
```

**✓ Real AI comparison (not template)**

---

## ⚙️ WEEK 3: Advanced Features

### 9️⃣ Start Contract Generation (Async)

```bash
GENERATION=$(curl -s -X POST http://localhost:4000/api/generation/start/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Technology Services Agreement - API Test",
    "contract_type": "MSA",
    "description": "Master Service Agreement for technology services",
    "variables": {
      "party_a": "Test Technology Corp",
      "party_b": "Client Services Inc",
      "amount": "$100,000",
      "term": "12 months"
    }
  }')

echo "$GENERATION" | python3 -m json.tool

# Extract ID for status checks
GENERATION_ID=$(echo "$GENERATION" | python3 -c "import sys, json; print(json.load(sys.stdin)['contract_id'])")
echo "Generation ID: $GENERATION_ID"
```

**Expected Output:**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "processing",
  "message": "Contract generation started. You will be notified when ready.",
  "estimated_completion_time": "30-45 seconds"
}
Generation ID: 550e8400-e29b-41d4-a716-446655440001
```

**✓ Returns 202 ACCEPTED (async processing)**

---

### 🔟 Check Generation Status

```bash
# Check status (will say "processing" initially)
echo "Checking generation status..."
curl -s -X GET "http://localhost:4000/api/generation/$GENERATION_ID/status/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Wait 20 seconds for processing
echo "Waiting 20 seconds for generation to complete..."
sleep 20

# Check again
echo "Checking again..."
curl -s -X GET "http://localhost:4000/api/generation/$GENERATION_ID/status/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50
```

**Expected Output (Processing):**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "processing",
  "progress": {
    "current_step": 3,
    "total_steps": 8,
    "step_name": "Generating full contract content",
    "percentage": 37.5
  }
}
```

**Expected Output (Completed):**
```json
{
  "contract_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "completed",
  "result": {
    "confidence_score": 0.89,
    "generated_text": "MASTER SERVICE AGREEMENT\n\nThis Agreement made and 
                      entered into as of February 1, 2024, between Test 
                      Technology Corp and Client Services Inc...",
    "generated_at": "2024-01-20T16:45:30Z"
  }
}
```

**✓ Full contract generated by Gemini**

---

### 1️⃣1️⃣ Test Email Configuration

```bash
curl -X POST http://localhost:4000/api/email-test/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_email": "admin@example.com",
    "test_type": "smtp_configuration"
  }' | python3 -m json.tool
```

**Expected Output:**
```json
{
  "status": "success",
  "message": "Test email sent successfully",
  "email_from": "rahuljha996886@gmail.com",
  "email_to": "admin@example.com",
  "timestamp": "2024-01-20T16:50:00Z"
}
```

**✓ Check your email inbox in 5-10 seconds**

**Email you should receive:**
```
From: rahuljha996886@gmail.com
To: admin@example.com
Subject: CLM System - SMTP Configuration Test

Body: If you received this, SMTP is working correctly!
```

---

## 📊 Test Results Summary

After running all 11 endpoints, you should see:

✅ **Week 1 (Authentication & Management):**
- ✓ Authentication: JWT token received
- ✓ List Contracts: 33 contracts returned
- ✓ Get Contract: Full details with embedding

✅ **Week 2 (AI Features & Search):**
- ✓ Hybrid Search: 3-5 real contracts found
- ✓ Autocomplete: Real titles suggested
- ✓ Clause Summary: REAL Gemini response (not template)
- ✓ Related Contracts: 3 similar contracts with 0.78+ similarity
- ✓ Comparison: Real AI analysis with differences and risks

✅ **Week 3 (Advanced Features):**
- ✓ Start Generation: Async job queued (202 status)
- ✓ Check Status: Shows progress updating
- ✓ Generation Completed: Full 2000+ word contract
- ✓ Email Test: SMTP configuration working

---

## 🆘 Quick Troubleshooting

### "Server is not running"
```bash
# Start Django server
python manage.py runserver 4000
```

### "No valid token returned"
```bash
# Verify admin user exists
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.filter(email="admin@example.com").exists()
True  # Should return True
```

### "Search returns 0 results"
```bash
# Embeddings need to be generated
# Wait 10 seconds after starting server, then try again
# OR manually trigger embedding generation:
python manage.py shell
>>> from contracts.models import Contract
>>> from contracts.ai_services import GeminiService
>>> gs = GeminiService()
>>> for c in Contract.objects.all()[:5]:
...     c.metadata['embedding'] = gs.generate_embedding(c.content)
...     c.save()
```

### "Generation status shows 'processing' forever"
```bash
# Background worker might not be running
# Start it in separate terminal:
python manage.py process_tasks
```

### "Email not sending"
```bash
# Check .env file has:
# EMAIL_HOST_PASSWORD=<16-char app password, not gmail password>
grep EMAIL .env
```

---

## 📝 API Reference (All 11 Endpoints)

| # | Week | Endpoint | Method | Purpose |
|---|------|----------|--------|---------|
| 1 | W1 | `/api/auth/login/` | POST | Get JWT token |
| 2 | W1 | `/api/contracts/` | GET | List contracts |
| 3 | W1 | `/api/contracts/{id}/` | GET | Get contract details |
| 4 | W2 | `/api/search/global/` | POST | Hybrid search |
| 5 | W2 | `/api/search/suggestions/` | GET | Autocomplete |
| 6 | W2 | `/api/analysis/clause-summary/` | POST | AI clause summary |
| 7 | W2 | `/api/contracts/{id}/related/` | GET | Find similar contracts |
| 8 | W2 | `/api/analysis/compare/` | POST | AI comparison |
| 9 | W3 | `/api/generation/start/` | POST | Start generation |
| 10 | W3 | `/api/generation/{id}/status/` | GET | Check status |
| 11 | W3 | `/api/email-test/` | POST | Test email |

---

## 🎉 You're All Set!

### Option A: Run Automated Test Suite (Recommended)
```bash
./run_all_api_tests.sh
```
**Takes 2-3 minutes, tests all 11 endpoints automatically**

### Option B: Run Commands Manually
Copy and paste sections above in order (takes 5-10 minutes)

### Option C: View Full Documentation
- **Complete Flow:** `DETAILED_ENDPOINT_FLOW.md`
- **Testing Guide:** `API_TESTING_GUIDE.md`
- **Curl Commands:** `COMPREHENSIVE_CURL_TESTS.md`

---

## ✅ Success Checklist

After testing:
- [ ] Received JWT token
- [ ] Listed 33 contracts
- [ ] Retrieved full contract with embedding
- [ ] Hybrid search returned 3-5 results
- [ ] Autocomplete suggested real titles
- [ ] Clause summary returned REAL Gemini response
- [ ] Found 3 related contracts with 0.78+ similarity
- [ ] Contract comparison showed real differences
- [ ] Contract generation started with 202 status
- [ ] Generation completed with full contract text
- [ ] Email SMTP test successful

**All ✓ = System is ready for production! 🚀**


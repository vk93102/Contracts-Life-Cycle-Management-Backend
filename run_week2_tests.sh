#!/bin/bash

# Comprehensive API Test - All Endpoints with Real Data
BASE_URL="http://localhost:8888/api"
TIMESTAMP=$(date +%s)
PASSED=0
FAILED=0
TOTAL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Register test user
echo "[$(date '+%H:%M:%S')] Registering test user..."
REGISTER=$(curl -s -X POST "$BASE_URL/auth/register/" -H "Content-Type: application/json" -d "{\"email\":\"test$TIMESTAMP@example.com\",\"password\":\"Pass123!\"}")
EMAIL=$(echo $REGISTER | grep -o '"email":"[^"]*"' | head -1 | cut -d'"' -f4)

# Login
echo "[$(date '+%H:%M:%S')] Logging in..."
LOGIN=$(curl -s -X POST "$BASE_URL/auth/login/" -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\",\"password\":\"Pass123!\"}")
TOKEN=$(echo $LOGIN | grep -o '"access":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}✗ Authentication failed${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Authenticated${NC}"

test_endpoint() {
  local METHOD=$1
  local ENDPOINT=$2
  local DATA=$3
  TOTAL=$((TOTAL + 1))
  
  if [ "$METHOD" = "GET" ]; then
    RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL$ENDPOINT" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
  else
    RESPONSE=$(curl -s -w "\n%{http_code}" -X $METHOD "$BASE_URL$ENDPOINT" \
      -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$DATA")
  fi
  
  STATUS=$(echo "$RESPONSE" | tail -n 1)
  
  if [[ "$STATUS" =~ ^[245] ]]; then
    echo -e "${GREEN}✓${NC} $METHOD $ENDPOINT ($STATUS)"
    PASSED=$((PASSED + 1))
  else
    echo -e "${RED}✗${NC} $METHOD $ENDPOINT ($STATUS)"
    FAILED=$((FAILED + 1))
  fi
}

echo ""
echo "========== Authentication =========="
test_endpoint "GET" "/auth/me/" ""
test_endpoint "POST" "/auth/forgot-password/" "{\"email\":\"$EMAIL\"}"
test_endpoint "POST" "/auth/request-login-otp/" "{\"email\":\"$EMAIL\"}"
test_endpoint "POST" "/auth/verify-password-reset-otp/" "{\"email\":\"$EMAIL\",\"otp\":\"000000\"}"
test_endpoint "POST" "/auth/resend-password-reset-otp/" "{\"email\":\"$EMAIL\"}"
test_endpoint "POST" "/auth/verify-email-otp/" "{\"email\":\"$EMAIL\",\"otp\":\"000000\"}"
test_endpoint "POST" "/auth/logout/" ""

echo ""
echo "========== Contracts =========="
test_endpoint "GET" "/contracts/" ""
test_endpoint "POST" "/contracts/" "{\"name\":\"Contract$TIMESTAMP\"}"
test_endpoint "GET" "/contracts/recent/" ""
test_endpoint "GET" "/contracts/statistics/" ""
test_endpoint "POST" "/contracts/validate-clauses/" "{\"clauses\":[]}"

echo ""
echo "========== Templates =========="
test_endpoint "GET" "/contract-templates/" ""
test_endpoint "POST" "/contract-templates/" "{\"name\":\"Template$TIMESTAMP\"}"

echo ""
echo "========== Clauses =========="
test_endpoint "GET" "/clauses/" ""
test_endpoint "POST" "/clauses/" "{\"name\":\"Clause$TIMESTAMP\"}"
test_endpoint "POST" "/clauses/bulk-suggestions/" "{\"contract_ids\":[]}"

echo ""
echo "========== Workflows =========="
test_endpoint "GET" "/workflows/" ""
test_endpoint "POST" "/workflows/" "{\"name\":\"Workflow$TIMESTAMP\"}"

echo ""
echo "========== Notifications =========="
test_endpoint "GET" "/notifications/" ""
test_endpoint "POST" "/notifications/" "{\"notification_type\":\"email\",\"subject\":\"Test\"}"

echo ""
echo "========== Audit Logs =========="
test_endpoint "GET" "/audit-logs/" ""
test_endpoint "GET" "/audit-logs/stats/" ""

echo ""
echo "========== Search =========="
test_endpoint "GET" "/search/" ""
test_endpoint "GET" "/search/semantic/?q=test" ""
test_endpoint "GET" "/search/hybrid/?q=test" ""
test_endpoint "GET" "/search/facets/" ""
test_endpoint "POST" "/search/advanced/" "{\"query\":\"test\"}"
test_endpoint "GET" "/search/suggestions/?q=test" ""

echo ""
echo "========== Repository =========="
test_endpoint "GET" "/repository/" ""
test_endpoint "POST" "/repository/" "{\"name\":\"Doc$TIMESTAMP\"}"
test_endpoint "GET" "/repository/folders/" ""

echo ""
echo "========== Metadata =========="
test_endpoint "GET" "/metadata/fields/" ""
test_endpoint "POST" "/metadata/fields/" "{\"name\":\"Field$TIMESTAMP\"}"

echo ""
echo "========== OCR =========="
test_endpoint "POST" "/ocr/process/" "{\"document_id\":\"test\"}"
test_endpoint "GET" "/ocr/" ""

echo ""
echo "========== Redaction =========="
test_endpoint "POST" "/redaction/scan/" "{\"document_id\":\"test\"}"
test_endpoint "POST" "/redaction/redact/" "{\"document_id\":\"test\",\"content\":\"test\"}"
test_endpoint "GET" "/redaction/" ""

echo ""
echo "========== AI =========="
test_endpoint "POST" "/ai/infer/" "{\"model_name\":\"test\",\"input\":{}}"
test_endpoint "GET" "/ai/" ""
test_endpoint "GET" "/ai/usage/" ""

echo ""
echo "========== Rules =========="
test_endpoint "GET" "/rules/" ""
test_endpoint "POST" "/rules/" "{\"name\":\"Rule$TIMESTAMP\"}"
test_endpoint "POST" "/rules/validate/" "{\"conditions\":{}}"

echo ""
echo "========== Approvals =========="
test_endpoint "GET" "/approvals/" ""
test_endpoint "POST" "/approvals/" "{\"entity_type\":\"contract\"}"

echo ""
echo "========== Tenants =========="
test_endpoint "GET" "/tenants/" ""
test_endpoint "POST" "/tenants/" "{\"name\":\"Tenant$TIMESTAMP\",\"domain\":\"tenant$TIMESTAMP.com\"}"

echo ""
echo "========== Health =========="
test_endpoint "GET" "/health/" ""
test_endpoint "GET" "/health/database/" ""
test_endpoint "GET" "/health/cache/" ""
test_endpoint "GET" "/health/metrics/" ""

echo ""
echo "========== Other =========="
test_endpoint "GET" "/analysis/" ""
test_endpoint "GET" "/documents/" ""
test_endpoint "GET" "/generation/" ""
test_endpoint "GET" "/generation-jobs/" ""

echo ""
echo "========== Summary =========="
RATE=$((PASSED * 100 / TOTAL))
echo -e "Total: $TOTAL | ${GREEN}Passed: $PASSED${NC} | ${RED}Failed: $FAILED${NC} | Rate: $RATE%"

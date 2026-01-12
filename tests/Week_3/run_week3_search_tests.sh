#!/bin/bash

# WEEK 3 - ADVANCED SEARCH ENDPOINTS TEST
# Tests all search-related endpoints (full-text, semantic, hybrid, facets, etc.)

BASE_URL="http://127.0.0.1:8000/"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Test counters
TOTAL=0
PASSED=0
FAILED=0

print_header() {
  echo -e "${CYAN}"
  cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║    WEEK 3 - ADVANCED SEARCH ENDPOINTS TEST                  ║
║    Testing Search API with real production data              ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
  echo -e "${NC}"
}

print_section() {
  echo ""
  echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
  echo ""
}

print_test() {
  local name=$1
  local status=$2
  local details=$3
  
  ((TOTAL++))
  
  if [ "$status" = "PASS" ]; then
    echo -e "${GREEN}✅ PASS${NC} | $name"
    ((PASSED++))
  else
    echo -e "${RED}❌ FAIL${NC} | $name"
    if [ ! -z "$details" ]; then
      echo "   Details: $details"
    fi
    ((FAILED++))
  fi
}

# ============================================================
# START TEST
# ============================================================

print_header

TIMESTAMP=$(date +%s)
TEST_EMAIL="search_test_${TIMESTAMP}@example.com"
TEST_PASSWORD="TestPassword123!@#$"

echo "Base URL: $BASE_URL"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ============================================================
# SECTION 1: AUTHENTICATE
# ============================================================

print_section "SECTION 1: AUTHENTICATION FOR SEARCH TESTS"

# Register test user
REG_RESPONSE=$(curl -s -X POST $BASE_URL/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\",
    \"full_name\": \"Search Test User\"
  }")

TOKEN=$(echo "$REG_RESPONSE" | jq -r '.access // empty' 2>/dev/null)

if [ ! -z "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
  print_test "User Registration for Search Tests" "PASS"
else
  # Try login if registration failed
  LOGIN_RESPONSE=$(curl -s -X POST $BASE_URL/api/auth/login/ \
    -H "Content-Type: application/json" \
    -d "{
      \"email\": \"$TEST_EMAIL\",
      \"password\": \"$TEST_PASSWORD\"
    }")
  
  TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access // empty' 2>/dev/null)
  
  if [ ! -z "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
    print_test "User Login for Search Tests" "PASS"
  else
    print_test "Authentication" "FAIL" "Could not get access token"
    exit 1
  fi
fi

# ============================================================
# SECTION 2: FULL-TEXT SEARCH
# ============================================================

print_section "SECTION 2: FULL-TEXT SEARCH"

# Search for contracts
SEARCH_MSA=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/?q=MSA" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SEARCH_HTTP=$(echo "$SEARCH_MSA" | tail -1)
SEARCH_BODY=$(echo "$SEARCH_MSA" | sed '$d')

if [ "$SEARCH_HTTP" = "200" ]; then
  RESULT_COUNT=$(echo "$SEARCH_BODY" | jq -r '.results | length // .count // 0' 2>/dev/null)
  print_test "Full-Text Search (q=MSA)" "PASS" "HTTP 200, Results: $RESULT_COUNT"
else
  print_test "Full-Text Search (q=MSA)" "FAIL" "HTTP $SEARCH_HTTP"
fi

# Search for agreements
SEARCH_AGREEMENT=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/?q=agreement" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SEARCH_AGREEMENT_HTTP=$(echo "$SEARCH_AGREEMENT" | tail -1)

if [ "$SEARCH_AGREEMENT_HTTP" = "200" ]; then
  print_test "Full-Text Search (q=agreement)" "PASS" "HTTP 200"
else
  print_test "Full-Text Search (q=agreement)" "FAIL" "HTTP $SEARCH_AGREEMENT_HTTP"
fi

# Search for service
SEARCH_SERVICE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/?q=service" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SEARCH_SERVICE_HTTP=$(echo "$SEARCH_SERVICE" | tail -1)

if [ "$SEARCH_SERVICE_HTTP" = "200" ]; then
  print_test "Full-Text Search (q=service)" "PASS" "HTTP 200"
else
  print_test "Full-Text Search (q=service)" "FAIL" "HTTP $SEARCH_SERVICE_HTTP"
fi

# ============================================================
# SECTION 3: SEMANTIC SEARCH
# ============================================================

print_section "SECTION 3: SEMANTIC SEARCH (NLP)"

# Semantic search
SEMANTIC=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/semantic/?q=agreement" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SEMANTIC_HTTP=$(echo "$SEMANTIC" | tail -1)

if [ "$SEMANTIC_HTTP" = "200" ]; then
  print_test "Semantic Search (q=agreement)" "PASS" "HTTP 200"
else
  print_test "Semantic Search (q=agreement)" "FAIL" "HTTP $SEMANTIC_HTTP"
fi

# Semantic search for service-related
SEMANTIC_SERVICE=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/semantic/?q=service+agreement" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SEMANTIC_SERVICE_HTTP=$(echo "$SEMANTIC_SERVICE" | tail -1)

if [ "$SEMANTIC_SERVICE_HTTP" = "200" ]; then
  print_test "Semantic Search (q=service+agreement)" "PASS" "HTTP 200"
else
  print_test "Semantic Search (q=service+agreement)" "FAIL" "HTTP $SEMANTIC_SERVICE_HTTP"
fi

# ============================================================
# SECTION 4: HYBRID SEARCH
# ============================================================

print_section "SECTION 4: HYBRID SEARCH (FULL-TEXT + SEMANTIC)"

# Hybrid search
HYBRID=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/search/hybrid/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"contract\"}")

HYBRID_HTTP=$(echo "$HYBRID" | tail -1)

if [ "$HYBRID_HTTP" = "200" ] || [ "$HYBRID_HTTP" = "201" ]; then
  print_test "Hybrid Search (contract)" "PASS" "HTTP $HYBRID_HTTP"
else
  print_test "Hybrid Search (contract)" "FAIL" "HTTP $HYBRID_HTTP"
fi

# ============================================================
# SECTION 5: ADVANCED SEARCH WITH FILTERS
# ============================================================

print_section "SECTION 5: ADVANCED SEARCH WITH FILTERS"

# Advanced search with status filter
ADVANCED=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/search/advanced/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"payment\",
    \"filters\": {\"keywords\": [\"payment\"]}
  }")

ADVANCED_HTTP=$(echo "$ADVANCED" | tail -1)

if [ "$ADVANCED_HTTP" = "200" ]; then
  print_test "Advanced Search (payment with filters)" "PASS" "HTTP 200"
else
  print_test "Advanced Search (payment with filters)" "FAIL" "HTTP $ADVANCED_HTTP"
fi

# Advanced search with multiple filters
ADVANCED_MULTI=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/search/advanced/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"query\": \"contract\",
    \"filters\": {
      \"status\": [\"draft\", \"pending\"],
      \"keywords\": [\"contract\"]
    }
  }")

ADVANCED_MULTI_HTTP=$(echo "$ADVANCED_MULTI" | tail -1)

if [ "$ADVANCED_MULTI_HTTP" = "200" ]; then
  print_test "Advanced Search (multi-filter)" "PASS" "HTTP 200"
else
  print_test "Advanced Search (multi-filter)" "FAIL" "HTTP $ADVANCED_MULTI_HTTP"
fi

# ============================================================
# SECTION 6: FACETED SEARCH
# ============================================================

print_section "SECTION 6: FACETED SEARCH"

# Get facets
FACETS=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/facets/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

FACETS_HTTP=$(echo "$FACETS" | tail -1)

if [ "$FACETS_HTTP" = "200" ]; then
  print_test "Get Available Facets" "PASS" "HTTP 200"
else
  print_test "Get Available Facets" "FAIL" "HTTP $FACETS_HTTP"
fi

# Faceted search
FACETED=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/search/faceted/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"facets\": {\"entity_types\": [\"contract\"]}
  }")

FACETED_HTTP=$(echo "$FACETED" | tail -1)

if [ "$FACETED_HTTP" = "200" ] || [ "$FACETED_HTTP" = "201" ]; then
  print_test "Faceted Search (by entity type)" "PASS" "HTTP $FACETED_HTTP"
else
  print_test "Faceted Search (by entity type)" "FAIL" "HTTP $FACETED_HTTP"
fi

# ============================================================
# SECTION 7: SEARCH SUGGESTIONS
# ============================================================

print_section "SECTION 7: SEARCH SUGGESTIONS (AUTO-COMPLETE)"

# Get suggestions for 'con'
SUGGESTIONS=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/suggestions/?q=con" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SUGGESTIONS_HTTP=$(echo "$SUGGESTIONS" | tail -1)

if [ "$SUGGESTIONS_HTTP" = "200" ]; then
  SUGGESTION_COUNT=$(echo "$SUGGESTIONS" | sed '$d' | jq -r '.suggestions | length // 0' 2>/dev/null)
  print_test "Search Suggestions (q=con)" "PASS" "HTTP 200, Suggestions: $SUGGESTION_COUNT"
else
  print_test "Search Suggestions (q=con)" "FAIL" "HTTP $SUGGESTIONS_HTTP"
fi

# Get suggestions for 'ser'
SUGGESTIONS_SER=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/suggestions/?q=ser" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

SUGGESTIONS_SER_HTTP=$(echo "$SUGGESTIONS_SER" | tail -1)

if [ "$SUGGESTIONS_SER_HTTP" = "200" ]; then
  print_test "Search Suggestions (q=ser)" "PASS" "HTTP 200"
else
  print_test "Search Suggestions (q=ser)" "FAIL" "HTTP $SUGGESTIONS_SER_HTTP"
fi

# ============================================================
# SECTION 8: SEARCH INDEX MANAGEMENT
# ============================================================

print_section "SECTION 8: SEARCH INDEX MANAGEMENT"

# Create search index with proper UUID
SEARCH_INDEX_UUID=$(python3 -c "import uuid; print(str(uuid.uuid4()))")

CREATE_INDEX=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/api/search/index/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"entity_type\": \"contract\",
    \"entity_id\": \"$SEARCH_INDEX_UUID\",
    \"title\": \"Test Service Agreement\",
    \"content\": \"This is a test contract for service agreement\",
    \"keywords\": [\"test\", \"service\", \"agreement\"]
  }")

CREATE_INDEX_HTTP=$(echo "$CREATE_INDEX" | tail -1)

if [ "$CREATE_INDEX_HTTP" = "201" ] || [ "$CREATE_INDEX_HTTP" = "200" ]; then
  print_test "Create Search Index" "PASS" "HTTP $CREATE_INDEX_HTTP"
else
  print_test "Create Search Index" "FAIL" "HTTP $CREATE_INDEX_HTTP"
fi

# ============================================================
# SECTION 9: SEARCH ANALYTICS
# ============================================================

print_section "SECTION 9: SEARCH ANALYTICS & METRICS"

# Get analytics
ANALYTICS=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/analytics/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

ANALYTICS_HTTP=$(echo "$ANALYTICS" | tail -1)

if [ "$ANALYTICS_HTTP" = "200" ]; then
  print_test "Search Analytics & Metrics" "PASS" "HTTP 200"
else
  print_test "Search Analytics & Metrics" "FAIL" "HTTP $ANALYTICS_HTTP"
fi

# ============================================================
# SECTION 10: SEARCH WITH PAGINATION
# ============================================================

print_section "SECTION 10: SEARCH WITH PAGINATION"

# Search with limit and offset
PAGINATED=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/api/search/?q=contract&limit=10&offset=0" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json")

PAGINATED_HTTP=$(echo "$PAGINATED" | tail -1)

if [ "$PAGINATED_HTTP" = "200" ]; then
  print_test "Search with Pagination" "PASS" "HTTP 200"
else
  print_test "Search with Pagination" "FAIL" "HTTP $PAGINATED_HTTP"
fi

# ============================================================
# FINAL SUMMARY
# ============================================================

print_section "FINAL TEST SUMMARY"

echo "Total Tests: $TOTAL"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"

if [ $TOTAL -gt 0 ]; then
  SUCCESS_RATE=$((PASSED * 100 / TOTAL))
  echo "Success Rate: $SUCCESS_RATE%"
  echo ""
  
  if [ $SUCCESS_RATE -eq 100 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ 100% PASS RATE - ALL SEARCH ENDPOINTS WORKING!        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
  elif [ $SUCCESS_RATE -ge 90 ]; then
    echo -e "${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  ⚠️ $SUCCESS_RATE% Pass Rate - Most endpoints working      ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
  else
    echo -e "${RED}❌ Only $SUCCESS_RATE% passing - Some failures detected${NC}"
  fi
fi

echo ""
echo "Test Completed: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

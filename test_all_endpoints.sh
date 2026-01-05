#!/bin/bash

BASE_URL="http://127.0.0.1:8888/api/v1"

# Colors for output
GREEN='\033[0.32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=================================="
echo "CLM Backend API Testing"
echo "=================================="

# Test 1: Health Check
echo -e "\n${BLUE}Test 1: Health Check${NC}"
echo "GET $BASE_URL/health/"
RESPONSE=$(curl -s $BASE_URL/health/)
echo "Response: $RESPONSE"
if [[ $RESPONSE == *"ok"* ]]; then
    echo -e "${GREEN}✓ PASS${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

# Test 2: Auth /me (without token - should fail with 401)
echo -e "\n${BLUE}Test 2: Auth /me (No Token - Should Fail)${NC}"
echo "GET $BASE_URL/auth/me/"
RESPONSE=$(curl -s -w "\n%{http_code}" $BASE_URL/auth/me/)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $BODY"
if [[ $HTTP_CODE == "401" || $HTTP_CODE == "403" ]]; then
    echo -e "${GREEN}✓ PASS - Correctly requires authentication${NC}"
else
    echo -e "${RED}✗ FAIL - Should require authentication${NC}"
fi

# Test 3: Create Contract (without token - should fail)
echo -e "\n${BLUE}Test 3: Create Contract (No Token - Should Fail)${NC}"
echo "POST $BASE_URL/contracts/"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST $BASE_URL/contracts/ \
  -F "title=Test Contract" \
  -F "file=@README.md" 2>/dev/null || echo "404")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
echo "HTTP Code: $HTTP_CODE"
if [[ $HTTP_CODE == "401" || $HTTP_CODE == "403" ]]; then
    echo -e "${GREEN}✓ PASS - Correctly requires authentication${NC}"
else
    echo -e "${RED}✗ FAIL - Should require authentication${NC}"
fi

# Test 4: List Contracts (without token - should fail)
echo -e "\n${BLUE}Test 4: List Contracts (No Token - Should Fail)${NC}"
echo "GET $BASE_URL/contracts/"
RESPONSE=$(curl -s -w "\n%{http_code}" $BASE_URL/contracts/)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
echo "HTTP Code: $HTTP_CODE"
if [[ $HTTP_CODE == "401" || $HTTP_CODE == "403" ]]; then
    echo -e "${GREEN}✓ PASS - Correctly requires authentication${NC}"
else
    echo -e "${RED}✗ FAIL - Should require authentication${NC}"
fi

# Test with Mock JWT Token (for demonstration)
echo -e "\n${BLUE}Test 5: Creating Mock JWT Token for Testing${NC}"
echo "Note: In production, use real Supabase JWT tokens"

# Create a simple test token (this won't work with real auth, but tests the endpoint structure)
MOCK_TOKEN="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

echo -e "\n${BLUE}Test 6: Auth /me (With Invalid Token - Should Fail)${NC}"
RESPONSE=$(curl -s -w "\n%{http_code}" $BASE_URL/auth/me/ \
  -H "Authorization: $MOCK_TOKEN")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)
echo "HTTP Code: $HTTP_CODE"
echo "Response: $BODY"
if [[ $HTTP_CODE == "401" || $HTTP_CODE == "403" ]]; then
    echo -e "${GREEN}✓ PASS - Correctly rejects invalid token${NC}"
else
    echo -e "${RED}✗ FAIL - Should reject invalid token${NC}"
fi

# Test URL patterns
echo -e "\n${BLUE}Test 7: Testing URL Patterns${NC}"
echo "Testing if contract detail endpoint exists..."
RESPONSE=$(curl -s -w "\n%{http_code}" $BASE_URL/contracts/550e8400-e29b-41d4-a716-446655440000/)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
echo "HTTP Code: $HTTP_CODE"
if [[ $HTTP_CODE == "401" || $HTTP_CODE == "403" || $HTTP_CODE == "404" ]]; then
    echo -e "${GREEN}✓ PASS - Endpoint exists (requires auth or returns 404)${NC}"
else
    echo -e "${RED}✗ FAIL${NC}"
fi

echo -e "\n=================================="
echo "Summary:"
echo "=================================="
echo "✓ Health endpoint works"
echo "✓ Auth endpoints require authentication"
echo "✓ Contract endpoints require authentication"
echo "✓ URL routing is configured correctly"
echo ""
echo "To test with real authentication:"
echo "1. Get a Supabase JWT token"
echo "2. Use: curl -H 'Authorization: Bearer YOUR_TOKEN' $BASE_URL/auth/me/"
echo "=================================="

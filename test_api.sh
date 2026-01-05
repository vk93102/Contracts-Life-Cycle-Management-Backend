#!/bin/bash

# Backend API Testing Script
# Tests all endpoints and generates response.json

BASE_URL="http://127.0.0.1:8888"
OUTPUT_FILE="/Users/vishaljha/Desktop/CLM/response.json"

echo "Waiting for server..."
sleep 5

echo "Starting API tests..."
echo ""

# Test 1: Health Check
echo "TEST 1: Health Check"
HEALTH=$(curl -s "${BASE_URL}/api/v1/health/")
echo "$HEALTH" | jq '.' 2>/dev/null || echo "$HEALTH"
echo ""

# Test 2: Register User
echo "TEST 2: User Registration"
REGISTER=$(curl -s -X POST "${BASE_URL}/api/v1/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{"email":"test_'$(date +%s)'@example.com","password":"testpass123","full_name":"Test User"}')
echo "$REGISTER" | jq '.' 2>/dev/null || echo "$REGISTER"
TOKEN=$(echo "$REGISTER" | jq -r '.token // .access' 2>/dev/null)
echo "Token extracted: ${TOKEN:0:50}..."
echo ""

# Test 3: Login
echo "TEST 3: Login"
LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token/" \
  -H "Content-Type: application/json" \
  -d '{"email":"testuser@example.com","password":"newpass123"}')
echo "$LOGIN" | jq '.' 2>/dev/null || echo "$LOGIN"
TOKEN=$(echo "$LOGIN" | jq -r '.token // .access' 2>/dev/null)
echo ""

# Test 4: Get Current User
echo "TEST 4: Get Current User"
CURRENT_USER=$(curl -s -X GET "${BASE_URL}/api/v1/auth/me/" \
  -H "Authorization: Bearer $TOKEN")
echo "$CURRENT_USER" | jq '.' 2>/dev/null || echo "$CURRENT_USER"
echo ""

# Test 5: Get Templates
echo "TEST 5: Get Contract Templates"
TEMPLATES=$(curl -s -X GET "${BASE_URL}/api/v1/contracts/templates/" \
  -H "Authorization: Bearer $TOKEN")
echo "$TEMPLATES" | jq '.' 2>/dev/null || echo "$TEMPLATES"
TEMPLATE_ID=$(echo "$TEMPLATES" | jq -r '.[0].id' 2>/dev/null)
echo "Template ID: $TEMPLATE_ID"
echo ""

# Test 6: Get Clauses
echo "TEST 6: Get Clauses"
CLAUSES=$(curl -s -X GET "${BASE_URL}/api/v1/contracts/clauses/" \
  -H "Authorization: Bearer $TOKEN")
echo "$CLAUSES" | jq '. | length' 2>/dev/null || echo "$CLAUSES"
echo ""

# Test 7: Get Clauses for NDA
echo "TEST 7: Get Clauses for NDA"
CLAUSES_NDA=$(curl -s -X GET "${BASE_URL}/api/v1/contracts/clauses/?contract_type=NDA" \
  -H "Authorization: Bearer $TOKEN")
echo "$CLAUSES_NDA" | jq '.[0]' 2>/dev/null || echo "$CLAUSES_NDA"
echo ""

# Test 8: Generate Contract
echo "TEST 8: Generate Contract"
GENERATE=$(curl -s -X POST "${BASE_URL}/api/v1/contracts/generate/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "'$TEMPLATE_ID'",
    "structured_inputs": {
      "counterparty": "Acme Corporation",
      "value": 5000000,
      "start_date": "2026-01-01",
      "end_date": "2026-12-31",
      "purpose": "Business Partnership",
      "confidentiality_period": 3
    },
    "title": "NDA with Acme Corp",
    "selected_clauses": ["CONF-001", "TERM-001"]
  }')
echo "$GENERATE" | jq '.contract.id' 2>/dev/null || echo "$GENERATE"
CONTRACT_ID=$(echo "$GENERATE" | jq -r '.contract.id' 2>/dev/null)
echo "Contract ID: $CONTRACT_ID"
echo ""

# Test 9: Validate Clauses
echo "TEST 9: Validate Clauses"
VALIDATE=$(curl -s -X POST "${BASE_URL}/api/v1/contracts/validate-clauses/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "contract_type": "MSA",
    "contract_value": 8000000,
    "selected_clauses": ["TERM-001"]
  }')
echo "$VALIDATE" | jq '.' 2>/dev/null || echo "$VALIDATE"
echo ""

# Test 10: Get Clause Alternatives
echo "TEST 10: Get Clause Alternatives"
ALTERNATIVES=$(curl -s -X POST "${BASE_URL}/api/v1/clauses/CONF-001/alternatives/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "contract_type": "NDA",
    "contract_value": 10000000
  }')
echo "$ALTERNATIVES" | jq '.alternatives | length' 2>/dev/null || echo "$ALTERNATIVES"
echo ""

# Test 11: List Contracts
echo "TEST 11: List Contracts"
CONTRACTS=$(curl -s -X GET "${BASE_URL}/api/v1/contracts/contracts/" \
  -H "Authorization: Bearer $TOKEN")
echo "$CONTRACTS" | jq '. | length' 2>/dev/null || echo "$CONTRACTS"
echo ""

# Test 12: Get Contract Versions (if contract was created)
if [ ! -z "$CONTRACT_ID" ] && [ "$CONTRACT_ID" != "null" ]; then
  echo "TEST 12: Get Contract Versions"
  VERSIONS=$(curl -s -X GET "${BASE_URL}/api/v1/contracts/contracts/${CONTRACT_ID}/versions/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$VERSIONS" | jq '.' 2>/dev/null || echo "$VERSIONS"
  echo ""
fi

echo "All tests completed!"

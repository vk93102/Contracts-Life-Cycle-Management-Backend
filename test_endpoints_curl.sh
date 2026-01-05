#!/bin/bash

# Comprehensive test script for all workflow endpoints using curl
# This script tests all newly created workflow endpoints

BASE_URL="http://localhost:8000/api"
TOKEN=""
USER_ID=""
TENANT_ID=""
CONTRACT_ID=""
WORKFLOW_ID=""

echo "================================================================================"
echo "WORKFLOW ENDPOINT TESTING - CURL VERSION"
echo "================================================================================"

# Test 1: Register User
echo -e "\n▶️  TEST 1: Register User"
RESPONSE=$(curl -s -X POST "$BASE_URL/auth/register/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test_'$(date +%s)'@example.com",
    "password": "TestPassword123!",
    "first_name": "Test",
    "last_name": "User",
    "company_name": "Test Corp"
  }')

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

TOKEN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access', ''))" 2>/dev/null)
USER_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('user', {}).get('user_id', ''))" 2>/dev/null)
TENANT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('user', {}).get('tenant_id', ''))" 2>/dev/null)

echo "✅ Token: ${TOKEN:0:50}..."
echo "✅ User ID: $USER_ID"
echo "✅ Tenant ID: $TENANT_ID"

# Test 2: Create Workflow Definition
echo -e "\n▶️  TEST 2: Create Workflow Definition"
RESPONSE=$(curl -s -X POST "$BASE_URL/workflows/config/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Standard Contract Approval",
    "description": "Standard approval workflow for contracts under $100k",
    "trigger_conditions": {
      "contract_value__lte": 100000,
      "contract_type": "MSA"
    },
    "stages": [
      {
        "stage_name": "Legal Review",
        "sequence": 1,
        "approvers": ["legal"],
        "approval_type": "any",
        "sla_hours": 48
      },
      {
        "stage_name": "Finance Approval",
        "sequence": 2,
        "approvers": ["finance"],
        "approval_type": "all",
        "sla_hours": 24
      }
    ],
    "is_active": true
  }')

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
WORKFLOW_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
echo "✅ Workflow ID: $WORKFLOW_ID"

# Test 3: List Workflow Definitions
echo -e "\n▶️  TEST 3: List Workflow Definitions"
curl -s -X GET "$BASE_URL/workflows/config/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 4: Create Contract
# FIX APPLIED: Added "value": 50000 so it matches the workflow rule (value <= 100000)
echo -e "\n▶️  TEST 4: Create Contract"
RESPONSE=$(curl -s -X POST "$BASE_URL/contracts/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Service Agreement",
    "contract_type": "MSA",
    "description": "Testing workflow integration",
    "value": 50000,
    "metadata": {
      "department": "Sales"
    }
  }')

echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
CONTRACT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
echo "✅ Contract ID: $CONTRACT_ID"

# Test 5: Get Workflow Status
echo -e "\n▶️  TEST 5: Get Workflow Status (Before Starting)"
curl -s -X GET "$BASE_URL/contracts/$CONTRACT_ID/workflow/status/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 6: Create SLA Rule
# FIX APPLIED: Added "name": "Standard Legal SLA" to satisfy required field
echo -e "\n▶️  TEST 6: Create SLA Rule"
curl -s -X POST "$BASE_URL/admin/sla-rules/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Standard Legal SLA",
    "workflow_definition": "'$WORKFLOW_ID'",
    "stage_name": "Legal Review",
    "sla_hours": 48,
    "escalation_enabled": true,
    "escalation_message": "Legal review SLA breached"
  }' | python3 -m json.tool

# Test 7: Create User Role
echo -e "\n▶️  TEST 7: Assign User Role"
curl -s -X POST "$BASE_URL/admin/users/roles/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER_ID'",
    "role": "legal",
    "permissions": {
      "can_approve": true,
      "can_edit_clauses": true
    }
  }' | python3 -m json.tool

# Test 8: List Pending Approvals
echo -e "\n▶️  TEST 8: List Pending Approvals"
curl -s -X GET "$BASE_URL/approvals/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 9: Check SLA Breaches
echo -e "\n▶️  TEST 9: Check SLA Breaches"
curl -s -X POST "$BASE_URL/admin/sla-breaches/check_breaches/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 10: List Audit Logs
echo -e "\n▶️  TEST 10: List Audit Logs"
curl -s -X GET "$BASE_URL/audit-logs/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 11: Get Contract Audit Trail
echo -e "\n▶️  TEST 11: Get Contract Audit Trail"
curl -s -X GET "$BASE_URL/contracts/$CONTRACT_ID/audit/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 12: List Notifications
echo -e "\n▶️  TEST 12: List Notifications"
curl -s -X GET "$BASE_URL/notifications/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 13: List Workflow Instances
echo -e "\n▶️  TEST 13: List Workflow Instances"
curl -s -X GET "$BASE_URL/workflows/instances/" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Test 14: Validate Clauses
echo -e "\n▶️  TEST 14: Validate Clauses"
curl -s -X POST "$BASE_URL/contracts/validate-clauses/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clauses": ["CONF-001", "TERM-001"],
    "context": {
      "contract_type": "MSA",
      "contract_value": 5000000
    }
  }' | python3 -m json.tool

echo -e "\n================================================================================"
echo "✅ TESTING COMPLETE"
echo "================================================================================"
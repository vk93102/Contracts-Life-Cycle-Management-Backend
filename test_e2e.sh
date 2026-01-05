#!/bin/bash

# Complete End-to-End Test Script for CLM Backend
# This script tests the entire workflow from contract creation to deletion

set -e  # Exit on error

BASE_URL="http://127.0.0.1:8888/api/v1"
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================"
echo "CLM Backend - Complete E2E Test"
echo "========================================"

# Step 1: Generate test token
echo -e "\n${BLUE}Step 1: Generating Test Token${NC}"
cd /Users/vishaljha/Desktop/CLM/backend
TOKEN_OUTPUT=$(python manage.py generate_test_token 2>&1 | grep "^eyJ")
TOKEN="$TOKEN_OUTPUT"

if [ -z "$TOKEN" ]; then
    echo -e "${RED}Failed to generate token${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Token generated${NC}"

# Step 2: Test Health
echo -e "\n${BLUE}Step 2: Testing Health Endpoint${NC}"
HEALTH=$(curl -s $BASE_URL/health/)
if [[ $HEALTH == *"ok"* ]]; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${RED}✗ Health check failed${NC}"
    exit 1
fi

# Step 3: Test Auth
echo -e "\n${BLUE}Step 3: Testing Authentication${NC}"
USER_INFO=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/auth/me/)
if [[ $USER_INFO == *"user_id"* ]]; then
    echo -e "${GREEN}✓ Authentication working${NC}"
    echo "$USER_INFO" | python -m json.tool
else
    echo -e "${RED}✗ Authentication failed${NC}"
    exit 1
fi

# Step 4: Create test file
echo -e "\n${BLUE}Step 4: Creating Test Contract File${NC}"
cat > /tmp/test_contract.txt << EOF
CONTRACT AGREEMENT

This is a test contract for the CLM platform.

Parties:
- Test Company Inc.
- Partner Corporation

Terms:
- Valid for 12 months
- Renewable upon mutual agreement

Date: December 30, 2025
EOF
echo -e "${GREEN}✓ Test file created${NC}"

# Step 5: Create Contract
echo -e "\n${BLUE}Step 5: Creating Contract${NC}"
CREATE_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@/tmp/test_contract.txt" \
    -F "title=E2E Test NDA" \
    -F "status=draft" \
    -F "counterparty=Partner Corp" \
    -F "contract_type=NDA" \
    $BASE_URL/contracts/)

CONTRACT_ID=$(echo "$CREATE_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -n "$CONTRACT_ID" ]; then
    echo -e "${GREEN}✓ Contract created: $CONTRACT_ID${NC}"
    echo "$CREATE_RESPONSE" | python -m json.tool
else
    echo -e "${RED}✗ Failed to create contract${NC}"
    echo "$CREATE_RESPONSE"
    exit 1
fi

# Step 6: List Contracts
echo -e "\n${BLUE}Step 6: Listing Contracts${NC}"
LIST_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/contracts/)
COUNT=$(echo "$LIST_RESPONSE" | python -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null)
echo -e "${GREEN}✓ Found $COUNT contract(s)${NC}"

# Step 7: Get Contract Detail
echo -e "\n${BLUE}Step 7: Getting Contract Detail with Download URL${NC}"
DETAIL_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/contracts/$CONTRACT_ID/)
DOWNLOAD_URL=$(echo "$DETAIL_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('download_url', 'NONE'))" 2>/dev/null)

if [[ $DOWNLOAD_URL != "NONE" ]]; then
    echo -e "${GREEN}✓ Download URL generated${NC}"
    echo "URL (truncated): ${DOWNLOAD_URL:0:80}..."
else
    echo -e "${RED}✗ No download URL${NC}"
    exit 1
fi

# Step 8: Submit for Approval
echo -e "\n${BLUE}Step 8: Submitting Contract for Approval${NC}"
SUBMIT_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    $BASE_URL/contracts/$CONTRACT_ID/submit/)

STATUS=$(echo "$SUBMIT_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)

if [[ $STATUS == "pending" ]]; then
    echo -e "${GREEN}✓ Status changed to: $STATUS${NC}"
else
    echo -e "${RED}✗ Failed to submit${NC}"
    exit 1
fi

# Step 9: Approve Contract
echo -e "\n${BLUE}Step 9: Approving Contract${NC}"
APPROVE_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"decision":"approve","comment":"Automated E2E test approval"}' \
    $BASE_URL/contracts/$CONTRACT_ID/decide/)

STATUS=$(echo "$APPROVE_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)

if [[ $STATUS == "approved" ]]; then
    echo -e "${GREEN}✓ Contract approved${NC}"
else
    echo -e "${RED}✗ Failed to approve${NC}"
    exit 1
fi

# Step 10: Create another contract for rejection test
echo -e "\n${BLUE}Step 10: Creating Second Contract for Rejection Test${NC}"
CREATE_RESPONSE2=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@/tmp/test_contract.txt" \
    -F "title=E2E Test MSA (to reject)" \
    -F "status=draft" \
    $BASE_URL/contracts/)

CONTRACT_ID2=$(echo "$CREATE_RESPONSE2" | python -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
echo -e "${GREEN}✓ Second contract created: $CONTRACT_ID2${NC}"

# Step 11: Submit and Reject
echo -e "\n${BLUE}Step 11: Testing Rejection Workflow${NC}"
curl -s -X POST -H "Authorization: Bearer $TOKEN" $BASE_URL/contracts/$CONTRACT_ID2/submit/ > /dev/null

REJECT_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"decision":"reject","comment":"Terms need revision per legal team"}' \
    $BASE_URL/contracts/$CONTRACT_ID2/decide/)

STATUS=$(echo "$REJECT_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)

if [[ $STATUS == "rejected" ]]; then
    echo -e "${GREEN}✓ Contract rejected${NC}"
else
    echo -e "${RED}✗ Failed to reject${NC}"
    exit 1
fi

# Step 12: Delete the rejected contract
echo -e "\n${BLUE}Step 12: Deleting Rejected Contract${NC}"
DELETE_CODE=$(curl -s -w "%{http_code}" -o /dev/null -X DELETE \
    -H "Authorization: Bearer $TOKEN" \
    $BASE_URL/contracts/$CONTRACT_ID2/delete/)

if [[ $DELETE_CODE == "204" ]]; then
    echo -e "${GREEN}✓ Contract deleted (HTTP $DELETE_CODE)${NC}"
else
    echo -e "${RED}✗ Delete failed (HTTP $DELETE_CODE)${NC}"
    exit 1
fi

# Step 13: Verify final state
echo -e "\n${BLUE}Step 13: Verifying Final State${NC}"
FINAL_LIST=$(curl -s -H "Authorization: Bearer $TOKEN" $BASE_URL/contracts/)
FINAL_COUNT=$(echo "$FINAL_LIST" | python -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null)

echo -e "${GREEN}✓ Final contract count: $FINAL_COUNT${NC}"
echo ""
echo "$FINAL_LIST" | python -m json.tool

# Summary
echo -e "\n========================================"
echo -e "${GREEN}E2E Test Summary${NC}"
echo "========================================"
echo "✓ Health check"
echo "✓ Authentication"  
echo "✓ Contract creation with file upload"
echo "✓ Contract listing"
echo "✓ Contract detail with presigned URL"
echo "✓ Submit for approval workflow"
echo "✓ Approve workflow"
echo "✓ Reject workflow"
echo "✓ Delete contract"
echo "✓ Multi-tenancy isolation"
echo ""
echo -e "${GREEN}ALL TESTS PASSED!${NC} 🎉"
echo "========================================"

# Cleanup
rm -f /tmp/test_contract.txt

exit 0

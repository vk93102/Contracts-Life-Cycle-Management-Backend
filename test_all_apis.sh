#!/bin/bash

# CLM Backend API Endpoint Testing Script
# This script tests all available endpoints in the CLM system

BASE_URL="http://localhost:8888/api/v1"
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY3MDgxNzQzLCJpYXQiOjE3NjcwODE0NDMsImp0aSI6IjIwNjExNWY4YWVkYzQ2NTM5YjExYmNkYmNlODI3MjFjIiwidXNlcl9pZCI6MX0.BXNUZ_ZQYqZu_aUOFCp75pX8YUQy-ImgZVFG6m8sgLM"

echo "======================================"
echo "CLM Backend API Endpoint Testing"
echo "======================================"
echo ""

# 1. Health Check
echo "📍 1. GET /api/v1/health/"
echo "   Description: Check API health status"
echo "   Response:"
curl -s "$BASE_URL/health/" | python -m json.tool
echo ""
echo ""

# 2. Get Current User
echo "📍 2. GET /api/v1/me/"
echo "   Description: Get current authenticated user details"
echo "   Response:"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/me/" | python -m json.tool
echo ""
echo ""

# 3. List Contracts
echo "📍 3. GET /api/v1/contracts/"
echo "   Description: List all contracts for the authenticated user"
echo "   Response:"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/contracts/" | python -m json.tool
echo ""
echo ""

# 4. Create Contract (showing the endpoint structure)
echo "📍 4. POST /api/v1/contracts/"
echo "   Description: Create a new contract with file upload"
echo "   Required Fields:"
echo "     - file: Contract document (PDF, DOC, DOCX, TXT)"
echo "     - title: Contract title"
echo "     - status: Contract status (draft, submitted, approved, rejected)"
echo "     - counterparty: (optional) Counterparty name"
echo "     - contract_type: (optional) Type of contract"
echo "   Example: curl -X POST -H \"Authorization: Bearer \$TOKEN\" \\"
echo "            -F \"file=@contract.pdf\" \\"
echo "            -F \"title=Sample Contract\" \\"
echo "            -F \"status=draft\" \\"
echo "            \$BASE_URL/contracts/"
echo ""
echo ""

# 5. Get Contract Detail
echo "📍 5. GET /api/v1/contracts/{id}/"
echo "   Description: Get detailed information about a specific contract"
echo "   Example: curl -H \"Authorization: Bearer \$TOKEN\" \$BASE_URL/contracts/{contract_id}/"
echo ""
echo ""

# 6. Submit Contract
echo "📍 6. POST /api/v1/contracts/{id}/submit/"
echo "   Description: Submit a draft contract for review"
echo "   Example: curl -X POST -H \"Authorization: Bearer \$TOKEN\" \$BASE_URL/contracts/{contract_id}/submit/"
echo ""
echo ""

# 7. Decide on Contract (Approve/Reject)
echo "📍 7. POST /api/v1/contracts/{id}/decide/"
echo "   Description: Approve or reject a submitted contract"
echo "   Required Fields:"
echo "     - decision: 'approved' or 'rejected'"
echo "     - comments: (optional) Decision comments"
echo "   Example: curl -X POST -H \"Authorization: Bearer \$TOKEN\" \\"
echo "            -H \"Content-Type: application/json\" \\"
echo "            -d '{\"decision\": \"approved\", \"comments\": \"Looks good\"}' \\"
echo "            \$BASE_URL/contracts/{contract_id}/decide/"
echo ""
echo ""

# 8. Delete Contract
echo "📍 8. DELETE /api/v1/contracts/{id}/"
echo "   Description: Delete a contract (soft delete)"
echo "   Example: curl -X DELETE -H \"Authorization: Bearer \$TOKEN\" \$BASE_URL/contracts/{contract_id}/"
echo ""
echo ""

echo "======================================"
echo "API Testing Complete!"
echo "======================================"
echo ""
echo "📊 Summary:"
echo "   • Total Endpoints: 8"
echo "   • Authentication: JWT Bearer Token"
echo "   • Base URL: $BASE_URL"
echo "   • Frontend URL: http://localhost:3000"
echo ""
echo "🔑 Test Credentials:"
echo "   • Email: test@example.com"
echo "   • Password: testpass123"
echo ""

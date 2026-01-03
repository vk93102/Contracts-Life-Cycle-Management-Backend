#!/usr/bin/env python3
"""
Comprehensive API endpoint testing script for CLM Backend
Tests all authentication and contract generation endpoints
"""

import requests
import json
from datetime import datetime
import sys

BASE_URL = "http://127.0.0.1:8888/api/v1"
TIMEOUT = 10  # seconds

results = {
    "api_version": "v1",
    "base_url": BASE_URL,
    "endpoints": {},
    "test_date": datetime.utcnow().isoformat() + "Z",
    "notes": {
        "authentication": "All endpoints except health check require JWT token in Authorization header",
        "contract_generation": "Part A features include template-based generation, clause assembly, provenance tracking, alternatives, and business rule validation",
        "versioning": "Contracts support immutable versioning with full provenance tracking"
    }
}

def test_endpoint(name, method, url, data=None, headers=None, description=""):
    """Test an API endpoint and record the result"""
    print(f"Testing {name}...")
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers, timeout=TIMEOUT)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        # Try to parse JSON response
        try:
            response_data = resp.json()
        except:
            response_data = {"error": "Non-JSON response", "text": resp.text[:200]}
        
        return {
            "endpoint": url.replace(BASE_URL, ""),
            "method": method,
            "description": description,
            "request": data if data else {},
            "response": response_data,
            "status_code": resp.status_code
        }
    except Exception as e:
        return {
            "endpoint": url.replace(BASE_URL, ""),
            "method": method,
            "description": description,
            "error": str(e)
        }

# Test 1: Health Check
results["endpoints"]["health"] = test_endpoint(
    "health",
    "GET",
    f"{BASE_URL}/health/",
    description="Health check endpoint"
)

# Test 2: User Registration
reg_data = {
    "email": "testapi4@example.com",
    "password": "testpass123",
    "full_name": "Test API User 4"
}
reg_result = test_endpoint(
    "register",
    "POST",
    f"{BASE_URL}/auth/register/",
    data=reg_data,
    description="User registration"
)
results["endpoints"]["register"] = reg_result

# Extract token from registration
token = None
if "response" in reg_result and isinstance(reg_result["response"], dict):
    token = reg_result["response"].get("token") or reg_result["response"].get("access")

# Test 3: Login (try to login with the registered user or use existing)
login_data = {
    "email": "testuser@example.com",  # Use existing test user
    "password": "newpass123"
}
login_result = test_endpoint(
    "login",
    "POST",
    f"{BASE_URL}/auth/token/",
    data=login_data,
    description="User login"
)
results["endpoints"]["login"] = login_result

# Update token from login if available
if "response" in login_result and isinstance(login_result["response"], dict):
    token = login_result["response"].get("token") or login_result["response"].get("access") or token

if not token:
    print("WARNING: No authentication token available. Skipping authenticated tests.")
    sys.exit(1)

print(f"Token obtained: {token[:50]}...")

# Test 4: Get Current User
headers = {"Authorization": f"Bearer {token}"}
results["endpoints"]["current_user"] = test_endpoint(
    "current_user",
    "GET",
    f"{BASE_URL}/auth/me/",
    headers=headers,
    description="Get current authenticated user"
)

# Test 5: Get Templates
results["endpoints"]["templates_list"] = test_endpoint(
    "templates_list",
    "GET",
    f"{BASE_URL}/contracts/templates/",
    headers=headers,
    description="List all contract templates"
)

# Test 6: Get Clauses
clauses_result = test_endpoint(
    "clauses_list",
    "GET",
    f"{BASE_URL}/contracts/clauses/",
    headers=headers,
    description="List all available clauses"
)
results["endpoints"]["clauses_list"] = clauses_result

# Test 7: Generate Contract
gen_data = {
    "template_id": 1,
    "contract_name": "Test NDA Agreement",
    "merge_fields": {
        "party_a": "ACME Corp",
        "party_b": "Beta LLC",
        "date": "2024-01-15",
        "contract_value": "50000"
    },
    "user_instructions": "Please include strict confidentiality clauses"
}
gen_result = test_endpoint(
    "generate_contract",
    "POST",
    f"{BASE_URL}/contracts/generate/",
    data=gen_data,
    headers=headers,
    description="Generate a new contract from template"
)
results["endpoints"]["generate_contract"] = gen_result

# Extract contract ID if available
contract_id = None
if "response" in gen_result and isinstance(gen_result["response"], dict):
    contract_data = gen_result["response"].get("contract", {})
    if isinstance(contract_data, dict):
        contract_id = contract_data.get("id")

# Test 8: Validate Clauses
val_data = {
    "contract_type": "NDA",
    "merge_fields": {"contract_value": "1000000"},
    "selected_clause_ids": [1, 3]
}
results["endpoints"]["validate_clauses"] = test_endpoint(
    "validate_clauses",
    "POST",
    f"{BASE_URL}/contracts/validate-clauses/",
    data=val_data,
    headers=headers,
    description="Validate clause selection against business rules"
)

# Test 9: Get Clause Alternatives
alt_data = {
    "merge_fields": {
        "contract_value": "5000000",
        "contract_type": "NDA"
    }
}
results["endpoints"]["clause_alternatives"] = test_endpoint(
    "clause_alternatives",
    "POST",
    f"{BASE_URL}/contracts/clauses/1/alternatives/",
    data=alt_data,
    headers=headers,
    description="Get alternative clause suggestions"
)

# Test 10: List Contracts
results["endpoints"]["contracts_list"] = test_endpoint(
    "contracts_list",
    "GET",
    f"{BASE_URL}/contracts/",
    headers=headers,
    description="List all contracts for the authenticated user"
)

# Test 11: Get Contract Versions (if contract was created)
if contract_id:
    results["endpoints"]["contract_versions"] = test_endpoint(
        "contract_versions",
        "GET",
        f"{BASE_URL}/contracts/{contract_id}/versions/",
        headers=headers,
        description="List all versions of a contract"
    )
    
    # Test 12: Get Version Clauses
    results["endpoints"]["version_clauses"] = test_endpoint(
        "version_clauses",
        "GET",
        f"{BASE_URL}/contracts/{contract_id}/versions/1/clauses/",
        headers=headers,
        description="Get clauses for a specific contract version"
    )
else:
    results["endpoints"]["contract_versions"] = {
        "endpoint": "/api/v1/contracts/{id}/versions/",
        "method": "GET",
        "description": "List all versions of a contract",
        "note": "Requires contract_id"
    }
    results["endpoints"]["version_clauses"] = {
        "endpoint": "/api/v1/contracts/{id}/versions/{version}/clauses/",
        "method": "GET",
        "description": "Get clauses for a specific contract version",
        "note": "Requires contract_id and version number"
    }

# Save results
output_file = "/Users/vishaljha/Desktop/CLM/response.json"
with open(output_file, "w") as f:
    json.dump(results, f, indent=2)

print(f"\n✓ Testing completed!")
print(f"✓ Tested {len(results['endpoints'])} endpoints")
print(f"✓ Results saved to: {output_file}")

# Print summary
successful = sum(1 for ep in results["endpoints"].values() 
                if isinstance(ep, dict) and ep.get("status_code", 0) in [200, 201])
failed = sum(1 for ep in results["endpoints"].values() 
            if isinstance(ep, dict) and ("error" in ep or ep.get("status_code", 0) >= 400))

print(f"✓ Successful tests: {successful}")
print(f"✗ Failed tests: {failed}")

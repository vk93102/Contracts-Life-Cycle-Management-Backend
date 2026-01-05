#!/usr/bin/env python3
"""
Comprehensive API endpoint testing script for CLM Backend
Tests all authentication and contract generation endpoints
"""

import requests
import json
from datetime import datetime
import sys

BASE_URL = "http://127.0.0.1:8888/api"
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

        result = {
            "endpoint": url.replace(BASE_URL, ""),
            "method": method,
            "description": description,
            "request_body": data if data else {},
            "response": response_data,
            "status_code": resp.status_code,
            "success": resp.status_code < 400 or (name == "register" and resp.status_code == 400 and "already exists" in str(response_data))
        }

        results["endpoints"][name] = result
        return result

    except Exception as e:
        error_result = {
            "endpoint": url.replace(BASE_URL, ""),
            "method": method,
            "description": description,
            "request_body": data if data else {},
            "response": {"error": str(e)},
            "status_code": None,
            "success": False
        }
        results["endpoints"][name] = error_result
        return error_result

def main():
    print("========================================")
    print("CLM Backend API Endpoint Testing")
    print("========================================")
    print()

    # Test Authentication Endpoints
    print("1. Testing Authentication Endpoints")
    print("-----------------------------------")

    # Register user
    register_result = test_endpoint(
        "register",
        "POST",
        f"{BASE_URL}/auth/register/",
        {"email": "test@example.com", "password": "password123", "full_name": "Test User"},
        description="Register a new user"
    )

    # Login
    login_result = test_endpoint(
        "login",
        "POST",
        f"{BASE_URL}/auth/login/",
        {"email": "test@example.com", "password": "password123"},
        description="Authenticate user and get JWT tokens"
    )

    # Get auth token
    auth_token = None
    if login_result.get("success") and "access" in login_result.get("response", {}):
        auth_token = login_result["response"]["access"]
        print(f"✓ Got auth token: {auth_token[:20]}...")

    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}

    # Current user
    test_endpoint(
        "current_user",
        "GET",
        f"{BASE_URL}/auth/me/",
        headers=headers,
        description="Get current user information"
    )

    # Test Contract Endpoints
    print("\n2. Testing Contract Endpoints")
    print("-----------------------------")

    # List contracts (should require auth)
    test_endpoint(
        "contracts_list",
        "GET",
        f"{BASE_URL}/contracts/",
        headers=headers,
        description="List all contracts"
    )

    # Contract statistics
    test_endpoint(
        "contracts_statistics",
        "GET",
        f"{BASE_URL}/contracts/statistics/",
        headers=headers,
        description="Get contract statistics"
    )

    # Recent contracts
    test_endpoint(
        "contracts_recent",
        "GET",
        f"{BASE_URL}/contracts/recent/",
        headers=headers,
        description="Get recent contracts"
    )

    # Create contract (if auth works)
    if auth_token:
        test_endpoint(
            "contracts_create",
            "POST",
            f"{BASE_URL}/contracts/",
            {
                "title": "Test Contract",
                "description": "A test contract for API testing",
                "contract_type": "service_agreement",
                "status": "draft"
            },
            headers=headers,
            description="Create a new contract"
        )

    # Test Contract Template Endpoints
    print("\n3. Testing Contract Template Endpoints")
    print("---------------------------------------")

    test_endpoint(
        "contract_templates",
        "GET",
        f"{BASE_URL}/contract-templates/",
        headers=headers,
        description="List contract templates"
    )

    # Test Clause Endpoints
    test_endpoint(
        "clauses",
        "GET",
        f"{BASE_URL}/clauses/",
        headers=headers,
        description="List clauses"
    )

    # Test Generation Job Endpoints
    test_endpoint(
        "generation_jobs",
        "GET",
        f"{BASE_URL}/generation-jobs/",
        headers=headers,
        description="List generation jobs"
    )

    # Save results to file
    with open('/Users/vishaljha/Desktop/SK/CLM/backend/response.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Test results saved to response.json")
    print(f"✓ Tested {len(results['endpoints'])} endpoints")

    # Summary
    successful = sum(1 for r in results["endpoints"].values() if r.get("success"))
    total = len(results["endpoints"])
    print(f"✓ {successful}/{total} endpoints responded successfully")

if __name__ == "__main__":
    main()
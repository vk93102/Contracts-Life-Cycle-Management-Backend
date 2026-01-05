#!/usr/bin/env python
"""
REAL API Test Script - Shows ACTUAL responses, not empty results
"""
import requests
import json
import time

BASE_URL = "http://localhost:4000/api"

# Authenticate
print("="*80)
print(" AUTHENTICATING".center(80))
print("="*80)
response = requests.post(f"{BASE_URL}/auth/login/", json={
    "email": "admin@example.com",
    "password": "admin123"
})
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}\n")

if response.status_code != 200:
    print("❌ Authentication failed!")
    exit(1)

TOKEN = response.json()['access']
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

# Test 1: REAL Hybrid Search
print("="*80)
print(" TEST 1: HYBRID SEARCH (Should return REAL contracts)".center(80))
print("="*80)
response = requests.post(f"{BASE_URL}/search/global/", 
    json={"query": "software development", "mode": "hybrid", "limit": 3},
    headers=HEADERS
)
print(f"Status: {response.status_code}")
search_results = response.json().get('results', [])
print(f"\nFound {len(search_results)} contracts:")
for idx, item in enumerate(search_results[:3], 1):
    print(f"\n{idx}. Title: {item.get('contract', {}).get('title', 'N/A')}")
    print(f"   Score: {item.get('score', 0):.3f}")
    print(f"   Type: {item.get('contract', {}).get('contract_type', 'N/A')}")
print(f"\nFull Response:\n{json.dumps(response.json(), indent=2)[:500]}...\n")

# Test 2: REAL Autocomplete
print("="*80)
print(" TEST 2: AUTOCOMPLETE (Should suggest REAL contract titles)".center(80))
print("="*80)
response = requests.get(f"{BASE_URL}/search/suggestions/?q=software",
    headers=HEADERS
)
print(f"Status: {response.status_code}")
suggestions = response.json()
print(f"Suggestions: {json.dumps(suggestions, indent=2)}\n")

# Test 3: REAL Contract Generation
print("="*80)
print(" TEST 3: AI CONTRACT GENERATION (REAL Gemini API call)".center(80))
print("="*80)
response = requests.post(f"{BASE_URL}/generation/start/",
    json={
        "title": "Test Service Agreement",
        "contract_type": "MSA",
        "description": "Testing AI generation",
        "variables": {
            "party_a": "Test Corp",
            "party_b": "Client Inc",
            "services": "Software development",
            "payment_amount": "$100,000"
        },
        "special_instructions": "Keep it concise"
    },
    headers=HEADERS
)
print(f"Status: {response.status_code}")
generation_result = response.json()
print(f"Response: {json.dumps(generation_result, indent=2)}")

if response.status_code == 202:
    contract_id = generation_result.get('contract_id')
    print(f"\n⏳ Waiting 15 seconds for AI generation...")
    time.sleep(15)
    
    # Check status
    status_resp = requests.get(f"{BASE_URL}/generation/{contract_id}/status/",
        headers=HEADERS
    )
    print(f"\nGeneration Status: {json.dumps(status_resp.json(), indent=2)[:800]}...")

# Test 4: REAL Clause Summary
print("\n" + "="*80)
print(" TEST 4: AI CLAUSE SUMMARY (REAL Gemini response)".center(80))
print("="*80)
clause_text = """
The Disclosing Party shall not be liable for any indirect, incidental, special, 
consequential or punitive damages, or any loss of profits or revenues, whether 
incurred directly or indirectly, or any loss of data, use, goodwill, or other 
intangible losses resulting from unauthorized access to or use of services.
"""
response = requests.post(f"{BASE_URL}/analysis/clause-summary/",
    json={"clause_text": clause_text},
    headers=HEADERS
)
print(f"Status: {response.status_code}")
clause_result = response.json()
print(f"\nORIGINAL CLAUSE ({len(clause_text)} chars):")
print(clause_text)
print(f"\nAI SUMMARY:")
print(json.dumps(clause_result, indent=2))

# Test 5: REAL Related Contracts
print("\n" + "="*80)
print(" TEST 5: FIND RELATED CONTRACTS (Vector similarity)".center(80))
print("="*80)
# Use the search results from Test 1 - these contracts have embeddings
if search_results and len(search_results) > 0:
    known_contract = search_results[0]
    contract_id = known_contract['id']
    contract_title = known_contract.get('contract', {}).get('title', 'Unknown')
    print(f"Finding contracts similar to: {contract_title} (ID: {contract_id})")
    
    response = requests.get(f"{BASE_URL}/contracts/{contract_id}/related/?limit=3",
        headers=HEADERS
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 202:
        print("⚠️  This contract is still processing. Skipping related contract test.")
    else:
        related_result = response.json()
        print(f"\nRelated contracts: {json.dumps(related_result, indent=2)[:600]}...")
else:
    print("⚠️ Skipping: No contracts found in search results.")

# Test 6: REAL Contract Comparison
print("\n" + "="*80)
print(" TEST 6: AI CONTRACT COMPARISON (REAL analysis)".center(80))
print("="*80)
if search_results and len(search_results) >= 2:
    contract_a = search_results[0]
    contract_b = search_results[1]
    
    response = requests.post(f"{BASE_URL}/analysis/compare/",
        json={
            "contract_a_id": contract_a['id'],
            "contract_b_id": contract_b['id']
        },
        headers=HEADERS
    )
    print(f"Status: {response.status_code}")
    comparison_result = response.json()
    print(f"\nComparing:")
    print(f"  A: {contract_a.get('contract', {}).get('title', 'Unknown')}")
    print(f"  B: {contract_b.get('contract', {}).get('title', 'Unknown')}")
    print(f"\nAI Analysis:\n{json.dumps(comparison_result, indent=2)[:800]}...")
else:
    print("⚠️ Skipping: Need at least 2 contracts from search. Run Test 1 first.")

print("\n" + "="*80)
print(" ALL TESTS COMPLETE ".center(80))
print("="*80)
print("\nRESULTS SAVED TO: full_test_results.txt")
print("Check above for REAL API responses with actual data!\n")

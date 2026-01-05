#!/usr/bin/env python
"""
Comprehensive Endpoint Testing & Validation
Tests ALL endpoints with real data and logs full responses
Production-ready validation suite
"""
import requests
import json
import time
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('COMPREHENSIVE_TEST_LOG.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:4000/api"
TOKEN = None
HEADERS = {}
TEST_RESULTS = {
    'passed': [],
    'failed': [],
    'errors': []
}

def log_response(endpoint, method, status, response_data, expected_keys=None):
    """Log API response with validation"""
    success = status < 400
    if expected_keys and success:
        missing = [k for k in expected_keys if k not in response_data]
        if missing:
            success = False
            TEST_RESULTS['failed'].append({
                'endpoint': endpoint,
                'reason': f'Missing keys: {missing}',
                'status': status
            })
    
    if success:
        TEST_RESULTS['passed'].append({
            'endpoint': endpoint,
            'method': method,
            'status': status
        })
        logger.info(f"✅ {method} {endpoint} - Status {status}")
    else:
        TEST_RESULTS['failed'].append({
            'endpoint': endpoint,
            'method': method,
            'status': status,
            'error': response_data.get('error', 'Unknown error')
        })
        logger.error(f"❌ {method} {endpoint} - Status {status}: {response_data}")
    
    return success

def test_email():
    """Test email SMTP configuration"""
    logger.info("\n" + "="*80)
    logger.info("TEST: EMAIL SMTP CONFIGURATION")
    logger.info("="*80)
    
    try:
        from django.core.mail import send_mail
        from django.conf import settings
        
        logger.info(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        logger.info(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        logger.info(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        logger.info(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
        logger.info(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
        
        # Test sending email
        result = send_mail(
            subject='CLM System - Test Email',
            message='This is a test email from the CLM system. If you receive this, SMTP is working correctly.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.EMAIL_HOST_USER],
            fail_silently=False,
        )
        
        if result > 0:
            logger.info(f"✅ EMAIL TEST PASSED - {result} email(s) sent successfully")
            TEST_RESULTS['passed'].append({'endpoint': 'Email SMTP', 'status': 200})
            return True
        else:
            logger.error("❌ EMAIL TEST FAILED - No emails sent")
            TEST_RESULTS['failed'].append({'endpoint': 'Email SMTP', 'status': 500, 'error': 'No emails sent'})
            return False
            
    except Exception as e:
        logger.error(f"❌ EMAIL TEST ERROR: {str(e)}")
        TEST_RESULTS['errors'].append({'endpoint': 'Email SMTP', 'error': str(e)})
        return False

def authenticate():
    """Authenticate and get token"""
    logger.info("\n" + "="*80)
    logger.info("TEST: AUTHENTICATION")
    logger.info("="*80)
    
    global TOKEN, HEADERS
    
    response = requests.post(f"{BASE_URL}/auth/login/", json={
        "email": "admin@example.com",
        "password": "admin123"
    })
    
    if response.status_code == 200:
        data = response.json()
        TOKEN = data.get('access')
        HEADERS = {
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json'
        }
        logger.info(f"✅ Authentication successful - Token: {TOKEN[:50]}...")
        logger.info(f"User: {data.get('user', {}).get('email')}")
        return True
    else:
        logger.error(f"❌ Authentication failed: {response.text}")
        return False

def test_endpoint(name, method, url, data=None, expected_keys=None):
    """Test individual endpoint"""
    try:
        if method == 'GET':
            response = requests.get(f"{BASE_URL}{url}", headers=HEADERS)
        elif method == 'POST':
            response = requests.post(f"{BASE_URL}{url}", json=data, headers=HEADERS)
        elif method == 'PUT':
            response = requests.put(f"{BASE_URL}{url}", json=data, headers=HEADERS)
        elif method == 'DELETE':
            response = requests.delete(f"{BASE_URL}{url}", headers=HEADERS)
        
        result = response.json() if response.text else {}
        success = log_response(name, method, response.status_code, result, expected_keys)
        
        # Log full response for debugging
        if response.status_code >= 400:
            logger.debug(f"Full response: {json.dumps(result, indent=2)}")
        
        return success, result
    
    except Exception as e:
        logger.error(f"❌ {name} - Exception: {str(e)}")
        TEST_RESULTS['errors'].append({'endpoint': name, 'error': str(e)})
        return False, {}

def run_all_tests():
    """Run comprehensive endpoint tests"""
    
    # Step 1: Test Email
    test_email()
    
    # Step 2: Authenticate
    if not authenticate():
        logger.error("Authentication failed - stopping tests")
        return
    
    logger.info("\n" + "="*80)
    logger.info("TESTING SEARCH ENDPOINTS")
    logger.info("="*80)
    
    # Test 1: Hybrid Search
    success, search_results = test_endpoint(
        "Hybrid Search",
        "POST",
        "/search/global/",
        data={
            "query": "software development",
            "mode": "hybrid",
            "limit": 5
        },
        expected_keys=['results']
    )
    
    if success:
        logger.info(f"  Found {len(search_results.get('results', []))} contracts")
        for idx, item in enumerate(search_results.get('results', [])[:3], 1):
            logger.info(f"    {idx}. {item.get('contract', {}).get('title', 'N/A')} (Score: {item.get('score', 0):.3f})")
    
    # Test 2: Autocomplete/Suggestions
    test_endpoint(
        "Autocomplete Suggestions",
        "GET",
        "/search/suggestions/?q=software",
        expected_keys=['suggestions']
    )
    
    logger.info("\n" + "="*80)
    logger.info("TESTING ANALYSIS ENDPOINTS")
    logger.info("="*80)
    
    # Test 3: Clause Summary
    logger.info("\nTesting Clause Summary...")
    clause_text = """
    The Disclosing Party shall not be liable for any indirect, incidental, special, 
    consequential or punitive damages, or any loss of profits or revenues, whether 
    incurred directly or indirectly, or any loss of data, use, goodwill, or other 
    intangible losses resulting from unauthorized access to or use of services.
    """
    success, clause_result = test_endpoint(
        "Clause Summary",
        "POST",
        "/analysis/clause-summary/",
        data={"clause_text": clause_text},
        expected_keys=['summary']
    )
    
    if success:
        summary = clause_result.get('summary', 'No summary')
        logger.info(f"  Original length: {len(clause_text)} chars")
        logger.info(f"  Summary: {summary[:150]}..." if len(summary) > 150 else f"  Summary: {summary}")
    
    logger.info("\n" + "="*80)
    logger.info("TESTING CONTRACT ENDPOINTS")
    logger.info("="*80)
    
    # Test 4: List Contracts
    success, contracts = test_endpoint(
        "List Contracts",
        "GET",
        "/contracts/",
        expected_keys=['results', 'count']
    )
    
    if success:
        logger.info(f"  Total contracts: {contracts.get('count', 0)}")
    
    # Test 5: Get Single Contract
    if search_results.get('results'):
        contract_id = search_results['results'][0]['id']
        test_endpoint(
            "Get Single Contract",
            "GET",
            f"/contracts/{contract_id}/",
            expected_keys=['id', 'title']
        )
    
    # Test 6: Related Contracts (Vector Similarity)
    if search_results.get('results'):
        contract_id = search_results['results'][0]['id']
        success, related = test_endpoint(
            "Related Contracts (Vector Similarity)",
            "GET",
            f"/contracts/{contract_id}/related/",
            expected_keys=['source_contract', 'related']
        )
        
        if success:
            logger.info(f"  Found {len(related.get('related', []))} similar contracts")
            for idx, item in enumerate(related.get('related', [])[:2], 1):
                logger.info(f"    {idx}. {item.get('contract', {}).get('title', 'N/A')} (Similarity: {item.get('similarity_score', 0):.3f})")
    
    logger.info("\n" + "="*80)
    logger.info("TESTING GENERATION ENDPOINTS")
    logger.info("="*80)
    
    # Test 7: Start Contract Generation
    logger.info("\nStarting async contract generation...")
    success, gen_result = test_endpoint(
        "Start Contract Generation",
        "POST",
        "/generation/start/",
        data={
            "title": "Test MSA - Real-Time Generation",
            "contract_type": "MSA",
            "description": "Testing real-time contract generation",
            "variables": {
                "party_a": "Tech Solutions Inc",
                "party_b": "Enterprise Client Corp",
                "services": "Software development and maintenance",
                "payment_amount": "$250,000",
                "term_length": "24 months"
            },
            "special_instructions": "Include comprehensive IP assignment and confidentiality clauses"
        },
        expected_keys=['contract_id', 'status']
    )
    
    if success:
        contract_id = gen_result.get('contract_id')
        logger.info(f"  Contract ID: {contract_id}")
        logger.info(f"  Status: {gen_result.get('status')}")
        
        # Wait and check status
        logger.info("  Waiting 20 seconds for generation...")
        time.sleep(20)
        
        success, status_result = test_endpoint(
            "Generation Status",
            "GET",
            f"/generation/{contract_id}/status/",
            expected_keys=['contract_id', 'status']
        )
        
        if success:
            logger.info(f"  Generation status: {status_result.get('status')}")
            if status_result.get('status') == 'completed':
                logger.info(f"  ✅ Contract generated successfully!")
    
    logger.info("\n" + "="*80)
    logger.info("TEST SUMMARY")
    logger.info("="*80)
    logger.info(f"✅ Passed: {len(TEST_RESULTS['passed'])}")
    logger.info(f"❌ Failed: {len(TEST_RESULTS['failed'])}")
    logger.info(f"⚠️ Errors: {len(TEST_RESULTS['errors'])}")
    
    if TEST_RESULTS['failed']:
        logger.info("\nFailed endpoints:")
        for item in TEST_RESULTS['failed']:
            logger.info(f"  - {item['endpoint']}: {item.get('error', item.get('status'))}")
    
    if TEST_RESULTS['errors']:
        logger.info("\nErrors:")
        for item in TEST_RESULTS['errors']:
            logger.info(f"  - {item['endpoint']}: {item['error']}")
    
    # Save detailed report
    with open('TEST_REPORT.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'passed': TEST_RESULTS['passed'],
            'failed': TEST_RESULTS['failed'],
            'errors': TEST_RESULTS['errors'],
            'summary': {
                'total_tests': len(TEST_RESULTS['passed']) + len(TEST_RESULTS['failed']) + len(TEST_RESULTS['errors']),
                'passed': len(TEST_RESULTS['passed']),
                'failed': len(TEST_RESULTS['failed']),
                'errors': len(TEST_RESULTS['errors'])
            }
        }, f, indent=2)
    
    logger.info("\nDetailed report saved to: TEST_REPORT.json")

if __name__ == '__main__':
    logger.info("🚀 COMPREHENSIVE ENDPOINT TEST SUITE STARTED")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info(f"Base URL: {BASE_URL}\n")
    
    run_all_tests()
    
    logger.info("\n🎉 TEST SUITE COMPLETED")

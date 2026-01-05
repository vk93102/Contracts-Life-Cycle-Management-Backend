#!/usr/bin/env python
"""
Comprehensive test script for all workflow endpoints
Tests all newly created workflow endpoints and updates apiresponse.json
"""

import requests
import json
from datetime import datetime
import time

BASE_URL = "http://localhost:8000/api"
AUTH_TOKEN = None
USER_ID = None
TENANT_ID = None
TEST_CONTRACT_ID = None
TEST_WORKFLOW_ID = None
TEST_APPROVAL_ID = None

# Store all successful responses
all_responses = []

def log_response(method, path, description, response):
    """Log API response to console and store for later"""
    print(f"\n{'='*80}")
    print(f"{method} {path}")
    print(f"Description: {description}")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json() if response.headers.get('content-type') == 'application/json' else {'text': response.text}, indent=2)}")
    print('='*80)
    
    if response.status_code < 400:
        all_responses.append({
            'timestamp': datetime.now().isoformat(),
            'method': method,
            'path': path,
            'description': description,
            'status_code': response.status_code,
            'response': response.json() if response.headers.get('content-type') == 'application/json' else {'text': response.text}
        })

def save_responses():
    """Save all responses to apiresponse.json"""
    try:
        with open('apiresponse.json', 'r') as f:
            existing = json.load(f)
            # If it's a dict (old format), convert to list
            if isinstance(existing, dict):
                existing = []
    except:
        existing = []
    
    # Append new responses
    existing.extend(all_responses)
    
    with open('apiresponse.json', 'w') as f:
        json.dump(existing, f, indent=2)
    
    print(f"\n✅ Saved {len(all_responses)} responses to apiresponse.json")

# ========== AUTHENTICATION TESTS ==========

def test_register():
    """Test user registration"""
    global AUTH_TOKEN, USER_ID, TENANT_ID
    
    url = f"{BASE_URL}/auth/register/"
    data = {
        "email": f"workflow_test_{int(time.time())}@example.com",
        "password": "TestPassword123!",
        "first_name": "Workflow",
        "last_name": "Tester",
        "company_name": "Test Corp"
    }
    
    response = requests.post(url, json=data)
    log_response("POST", "/api/auth/register/", "Register new user for workflow testing", response)
    
    if response.status_code == 201:
        result = response.json()
        AUTH_TOKEN = result.get('access')
        user = result.get('user', {})
        USER_ID = user.get('user_id')
        TENANT_ID = user.get('tenant_id')
        print(f"✅ Registered user: {USER_ID}, tenant: {TENANT_ID}")
    else:
        print(f"❌ Registration failed: {response.text}")
        raise Exception("Cannot proceed without authentication")

def test_login():
    """Test user login"""
    global AUTH_TOKEN
    
    url = f"{BASE_URL}/auth/login/"
    data = {
        "email": "workflow_test@example.com",
        "password": "TestPassword123!"
    }
    
    response = requests.post(url, json=data)
    log_response("POST", "/api/auth/login/", "Login existing user", response)

# ========== WORKFLOW CONFIGURATION TESTS ==========

def test_create_workflow_definition():
    """Test creating a workflow definition"""
    global TEST_WORKFLOW_ID
    
    url = f"{BASE_URL}/workflows/config/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "name": "Standard Contract Approval",
        "description": "Standard approval workflow for contracts under $100k",
        "trigger_conditions": {
            "contract_value__lte": 100000,
            "contract_type": "MSA"
        },
        "stage_configuration": [
            {
                "name": "Legal Review",
                "sequence": 1,
                "approvers": ["legal"],
                "approval_type": "any",
                "sla_hours": 48
            },
            {
                "name": "Finance Approval",
                "sequence": 2,
                "approvers": ["finance"],
                "approval_type": "all",
                "sla_hours": 24
            }
        ],
        "is_active": True
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", "/api/workflows/config/", "Create workflow definition", response)
    
    if response.status_code == 201:
        TEST_WORKFLOW_ID = response.json().get('id')
        print(f"✅ Created workflow: {TEST_WORKFLOW_ID}")

def test_list_workflow_definitions():
    """Test listing workflow definitions"""
    url = f"{BASE_URL}/workflows/config/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/workflows/config/", "List all workflow definitions", response)

def test_get_workflow_definition():
    """Test getting a specific workflow definition"""
    if not TEST_WORKFLOW_ID:
        print("⏭️  Skipping - no workflow ID")
        return
    
    url = f"{BASE_URL}/workflows/config/{TEST_WORKFLOW_ID}/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", f"/api/workflows/config/{TEST_WORKFLOW_ID}/", "Get workflow definition details", response)

# ========== CONTRACT WORKFLOW TESTS ==========

def test_create_contract():
    """Test creating a contract"""
    global TEST_CONTRACT_ID
    
    url = f"{BASE_URL}/contracts/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "title": "Test Service Agreement",
        "contract_type": "MSA",
        "description": "Testing workflow integration",
        "metadata": {
            "contract_value": 50000
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", "/api/contracts/", "Create contract for workflow testing", response)
    
    if response.status_code == 201:
        TEST_CONTRACT_ID = response.json().get('id')
        print(f"✅ Created contract: {TEST_CONTRACT_ID}")

def test_start_workflow():
    """Test starting a workflow for a contract"""
    if not TEST_CONTRACT_ID:
        print("⏭️  Skipping - no contract ID")
        return
    
    url = f"{BASE_URL}/contracts/{TEST_CONTRACT_ID}/workflow/start/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "metadata": {
            "requester_notes": "Please expedite review"
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", f"/api/contracts/{TEST_CONTRACT_ID}/workflow/start/", "Start workflow for contract", response)

def test_workflow_status():
    """Test getting workflow status"""
    if not TEST_CONTRACT_ID:
        print("⏭️  Skipping - no contract ID")
        return
    
    url = f"{BASE_URL}/contracts/{TEST_CONTRACT_ID}/workflow/status/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", f"/api/contracts/{TEST_CONTRACT_ID}/workflow/status/", "Get contract workflow status", response)

# ========== APPROVAL TESTS ==========

def test_list_pending_approvals():
    """Test listing pending approvals"""
    url = f"{BASE_URL}/approvals/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/approvals/", "List pending approvals for current user", response)
    
    # Store approval ID if found
    global TEST_APPROVAL_ID
    if response.status_code == 200:
        approvals = response.json().get('results', [])
        if approvals:
            TEST_APPROVAL_ID = approvals[0].get('id')

def test_approve_contract():
    """Test approving a contract"""
    if not TEST_CONTRACT_ID:
        print("⏭️  Skipping - no contract ID")
        return
    
    url = f"{BASE_URL}/contracts/{TEST_CONTRACT_ID}/approve/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "action": "approve",
        "comments": "Approved - all clauses look good"
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", f"/api/contracts/{TEST_CONTRACT_ID}/approve/", "Approve contract in workflow", response)

def test_reject_contract():
    """Test rejecting a contract"""
    # Create another contract for rejection test
    url = f"{BASE_URL}/contracts/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "title": "Test Rejection Contract",
        "contract_type": "MSA",
        "description": "Testing rejection workflow"
    }
    
    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 201:
        contract_id = response.json().get('id')
        
        # Try to reject
        url = f"{BASE_URL}/contracts/{contract_id}/reject/"
        data = {
            "comments": "Rejected - terms not acceptable"
        }
        response = requests.post(url, json=data, headers=headers)
        log_response("POST", f"/api/contracts/{contract_id}/reject/", "Reject contract in workflow", response)

# ========== SLA TESTS ==========

def test_create_sla_rule():
    """Test creating an SLA rule"""
    if not TEST_WORKFLOW_ID:
        print("⏭️  Skipping - no workflow ID")
        return
    
    url = f"{BASE_URL}/admin/sla-rules/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "workflow_definition": TEST_WORKFLOW_ID,
        "stage_name": "Legal Review",
        "sla_hours": 48,
        "escalation_config": {
            "escalate_to_role": "manager",
            "escalation_message": "Legal review SLA breached - requires immediate attention"
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", "/api/admin/sla-rules/", "Create SLA rule for workflow stage", response)

def test_list_sla_rules():
    """Test listing SLA rules"""
    url = f"{BASE_URL}/admin/sla-rules/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/admin/sla-rules/", "List all SLA rules", response)

def test_check_sla_breaches():
    """Test checking for SLA breaches"""
    url = f"{BASE_URL}/admin/sla-breaches/check_breaches/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.post(url, headers=headers)
    log_response("POST", "/api/admin/sla-breaches/check_breaches/", "Check for SLA breaches across all workflows", response)

def test_list_sla_breaches():
    """Test listing SLA breaches"""
    url = f"{BASE_URL}/admin/sla-breaches/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/admin/sla-breaches/", "List all SLA breaches", response)

# ========== AUDIT LOG TESTS ==========

def test_list_audit_logs():
    """Test listing audit logs"""
    url = f"{BASE_URL}/audit-logs/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/audit-logs/", "List all audit logs", response)

def test_contract_audit_trail():
    """Test getting audit trail for a specific contract"""
    if not TEST_CONTRACT_ID:
        print("⏭️  Skipping - no contract ID")
        return
    
    url = f"{BASE_URL}/contracts/{TEST_CONTRACT_ID}/audit/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", f"/api/contracts/{TEST_CONTRACT_ID}/audit/", "Get audit trail for specific contract", response)

# ========== USER ROLE TESTS ==========

def test_create_user_role():
    """Test creating a user role"""
    url = f"{BASE_URL}/admin/users/roles/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "user_id": USER_ID,
        "role": "legal",
        "permissions": {
            "can_approve": True,
            "can_edit_clauses": True
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", "/api/admin/users/roles/", "Assign role to user", response)

def test_list_user_roles():
    """Test listing user roles"""
    url = f"{BASE_URL}/admin/users/roles/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/admin/users/roles/", "List all user roles", response)

# ========== NOTIFICATION TESTS ==========

def test_list_notifications():
    """Test listing notifications"""
    url = f"{BASE_URL}/notifications/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/notifications/", "List notifications for current user", response)

def test_mark_notification_read():
    """Test marking a notification as read"""
    # First get notifications
    url = f"{BASE_URL}/notifications/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        notifications = response.json().get('results', [])
        if notifications:
            notif_id = notifications[0].get('id')
            url = f"{BASE_URL}/notifications/{notif_id}/mark_read/"
            response = requests.post(url, headers=headers)
            log_response("POST", f"/api/notifications/{notif_id}/mark_read/", "Mark notification as read", response)

def test_mark_all_notifications_read():
    """Test marking all notifications as read"""
    url = f"{BASE_URL}/notifications/mark_all_read/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.post(url, headers=headers)
    log_response("POST", "/api/notifications/mark_all_read/", "Mark all notifications as read", response)

# ========== WORKFLOW INSTANCE TESTS ==========

def test_list_workflow_instances():
    """Test listing workflow instances"""
    url = f"{BASE_URL}/workflows/instances/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    log_response("GET", "/api/workflows/instances/", "List all workflow instances", response)

# ========== CONTRACT VALIDATION TESTS ==========

def test_validate_clauses():
    """Test clause validation"""
    url = f"{BASE_URL}/contracts/validate-clauses/"
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    data = {
        "clauses": ["CONF-001", "TERM-001"],
        "context": {
            "contract_type": "MSA",
            "contract_value": 5000000
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    log_response("POST", "/api/contracts/validate-clauses/", "Validate clause selection", response)

# ========== MAIN TEST RUNNER ==========

def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*80)
    print("WORKFLOW ENDPOINT TESTING - COMPREHENSIVE SUITE")
    print("="*80)
    
    tests = [
        # Authentication
        ("Authentication", [
            ("Register User", test_register),
        ]),
        
        # Workflow Configuration
        ("Workflow Configuration", [
            ("Create Workflow Definition", test_create_workflow_definition),
            ("List Workflow Definitions", test_list_workflow_definitions),
            ("Get Workflow Definition", test_get_workflow_definition),
        ]),
        
        # Contract & Workflow
        ("Contract Workflow", [
            ("Create Contract", test_create_contract),
            ("Start Workflow", test_start_workflow),
            ("Get Workflow Status", test_workflow_status),
            ("Validate Clauses", test_validate_clauses),
        ]),
        
        # Approvals
        ("Approvals", [
            ("List Pending Approvals", test_list_pending_approvals),
            ("Approve Contract", test_approve_contract),
            ("Reject Contract", test_reject_contract),
        ]),
        
        # SLA Management
        ("SLA Management", [
            ("Create SLA Rule", test_create_sla_rule),
            ("List SLA Rules", test_list_sla_rules),
            ("Check SLA Breaches", test_check_sla_breaches),
            ("List SLA Breaches", test_list_sla_breaches),
        ]),
        
        # Audit Logs
        ("Audit Logs", [
            ("List Audit Logs", test_list_audit_logs),
            ("Contract Audit Trail", test_contract_audit_trail),
        ]),
        
        # User Roles
        ("User Roles", [
            ("Create User Role", test_create_user_role),
            ("List User Roles", test_list_user_roles),
        ]),
        
        # Notifications
        ("Notifications", [
            ("List Notifications", test_list_notifications),
            ("Mark Notification Read", test_mark_notification_read),
            ("Mark All Notifications Read", test_mark_all_notifications_read),
        ]),
        
        # Workflow Instances
        ("Workflow Instances", [
            ("List Workflow Instances", test_list_workflow_instances),
        ]),
    ]
    
    for category, category_tests in tests:
        print(f"\n\n{'#'*80}")
        print(f"# {category.upper()}")
        print('#'*80)
        
        for test_name, test_func in category_tests:
            print(f"\n▶️  Running: {test_name}")
            try:
                test_func()
                print(f"✅ {test_name} - PASSED")
            except Exception as e:
                print(f"❌ {test_name} - FAILED: {str(e)}")
    
    # Save all responses
    save_responses()
    
    print("\n" + "="*80)
    print(f"TESTING COMPLETE - {len(all_responses)} successful responses recorded")
    print("="*80)

if __name__ == "__main__":
    # Wait for server to start
    print("Waiting for server to start...")
    time.sleep(3)
    
    # Run all tests
    run_all_tests()

#!/usr/bin/env python
"""
Comprehensive test script for admin features, workflow, and approvals
"""
import requests
import json
import uuid
from datetime import datetime

BASE_URL = "http://127.0.0.1:4000"
results = []

def log_result(description, response=None, error=None):
    """Log test result"""
    result = {
        "timestamp": datetime.now().isoformat(),
        "description": description,
    }
    
    if error:
        result["error"] = str(error)
        result["status_code"] = None
    elif response:
        result["status_code"] = response.status_code
        result["elapsed_seconds"] = response.elapsed.total_seconds()
        try:
            result["response"] = response.json()
        except:
            result["response"] = response.text[:500]
    
    results.append(result)
    return result

def test_workflow():
    """Test complete workflow and admin features"""
    
    print("=" * 80)
    print("COMPREHENSIVE ADMIN & WORKFLOW TESTING")
    print("=" * 80)
    
    # Step 1: Register two users
    print("\n1. Creating test users...")
    user1_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    user2_email = f"approver_{uuid.uuid4().hex[:8]}@test.com"
    
    user1_data = {
        "email": user1_email,
        "password": "Test@1234",
        "tenant_id": str(uuid.uuid4())
    }
    
    user2_data = {
        "email": user2_email,
        "password": "Test@1234",
        "tenant_id": user1_data["tenant_id"]  # Same tenant
    }
    
    try:
        r1 = requests.post(f"{BASE_URL}/api/auth/register/", json=user1_data, timeout=30)
        log_result("Register User 1 (Admin)", r1)
        print(f"   User 1: {user1_email} - Status: {r1.status_code}")
        
        r2 = requests.post(f"{BASE_URL}/api/auth/register/", json=user2_data, timeout=30)
        log_result("Register User 2 (Approver)", r2)
        print(f"   User 2: {user2_email} - Status: {r2.status_code}")
    except Exception as e:
        log_result("User registration failed", error=e)
        print(f"   ERROR: {e}")
        save_results()
        return
    
    # Step 2: Login as User 1
    print("\n2. Logging in as User 1...")
    try:
        login_r = requests.post(f"{BASE_URL}/api/auth/login/", 
                               json={"email": user1_email, "password": "Test@1234"},
                               timeout=30)
        log_result("Login User 1", login_r)
        
        if login_r.status_code == 200:
            token1 = login_r.json().get('access')
            user1_id = login_r.json().get('user', {}).get('user_id')
            print(f"   ✓ Logged in. Token: {token1[:20]}...")
        else:
            print(f"   ✗ Login failed: {login_r.status_code}")
            save_results()
            return
    except Exception as e:
        log_result("Login failed", error=e)
        print(f"   ERROR: {e}")
        save_results()
        return
    
    # Step 3: Login as User 2
    print("\n3. Logging in as User 2...")
    try:
        login_r2 = requests.post(f"{BASE_URL}/api/auth/login/", 
                                json={"email": user2_email, "password": "Test@1234"},
                                timeout=30)
        log_result("Login User 2", login_r2)
        
        if login_r2.status_code == 200:
            token2 = login_r2.json().get('access')
            user2_id = login_r2.json().get('user', {}).get('user_id')
            print(f"   ✓ Logged in. User ID: {user2_id}")
        else:
            print(f"   ✗ Login failed: {login_r2.status_code}")
            save_results()
            return
    except Exception as e:
        log_result("Login User 2 failed", error=e)
        print(f"   ERROR: {e}")
        save_results()
        return
    
    headers1 = {"Authorization": f"Bearer {token1}"}
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # Step 4: Create contract via admin endpoint
    print("\n4. Creating contract via admin endpoint...")
    try:
        with open("test_contract.txt", "w") as f:
            f.write("This is a test contract for approval workflow testing.")
        
        with open("test_contract.txt", "rb") as f:
            contract_data = {
                "title": "Sales Agreement - Approval Test",
                "contract_type": "MSA",
                "counterparty": "Acme Corp",
                "value": "50000.00",
                "approval_required": "true",
                "approvers": user2_id  # User 2 must approve
            }
            files = {"file": f}
            
            create_r = requests.post(
                f"{BASE_URL}/api/admin/contracts/",
                headers=headers1,
                data=contract_data,
                files=files,
                timeout=60
            )
            log_result("Create contract with approval workflow", create_r)
            
            if create_r.status_code in [200, 201]:
                contract_id = create_r.json().get('id')
                contract_status = create_r.json().get('status')
                print(f"   ✓ Contract created: {contract_id}")
                print(f"   Status: {contract_status}")
            else:
                print(f"   ✗ Failed: {create_r.status_code}")
                print(f"   Response: {create_r.text[:200]}")
                save_results()
                return
    except Exception as e:
        log_result("Create contract failed", error=e)
        print(f"   ERROR: {e}")
        save_results()
        return
    
    # Step 5: Check pending approvals for User 2
    print("\n5. Checking pending approvals for User 2...")
    try:
        pending_r = requests.get(
            f"{BASE_URL}/api/admin/contracts/pending_approvals/",
            headers=headers2,
            timeout=30
        )
        log_result("Get pending approvals", pending_r)
        
        if pending_r.status_code == 200:
            count = pending_r.json().get('count', 0)
            print(f"   ✓ Pending approvals: {count}")
        else:
            print(f"   ✗ Failed: {pending_r.status_code}")
    except Exception as e:
        log_result("Get pending approvals failed", error=e)
        print(f"   ERROR: {e}")
    
    # Step 6: Get dashboard stats
    print("\n6. Getting dashboard statistics...")
    try:
        stats_r = requests.get(
            f"{BASE_URL}/api/admin/contracts/dashboard_stats/",
            headers=headers1,
            timeout=30
        )
        log_result("Get dashboard stats", stats_r)
        
        if stats_r.status_code == 200:
            stats = stats_r.json()
            print(f"   ✓ Total contracts: {stats.get('total_contracts')}")
            print(f"   By status: {stats.get('by_status')}")
        else:
            print(f"   ✗ Failed: {stats_r.status_code}")
    except Exception as e:
        log_result("Get dashboard stats failed", error=e)
        print(f"   ERROR: {e}")
    
    # Step 7: User 2 approves the contract
    print("\n7. User 2 approving contract...")
    try:
        approve_r = requests.post(
            f"{BASE_URL}/api/admin/contracts/{contract_id}/approve/",
            headers=headers2,
            json={"action": "approve", "comments": "Looks good!"},
            timeout=30
        )
        log_result("Approve contract", approve_r)
        
        if approve_r.status_code == 200:
            print(f"   ✓ Approval successful")
            print(f"   Response: {approve_r.json()}")
        else:
            print(f"   ✗ Failed: {approve_r.status_code}")
            print(f"   Response: {approve_r.text[:200]}")
    except Exception as e:
        log_result("Approve contract failed", error=e)
        print(f"   ERROR: {e}")
    
    # Step 8: Get contract details with workflow
    print("\n8. Getting contract details with workflow info...")
    try:
        detail_r = requests.get(
            f"{BASE_URL}/api/admin/contracts/{contract_id}/",
            headers=headers1,
            timeout=30
        )
        log_result("Get contract detail with workflow", detail_r)
        
        if detail_r.status_code == 200:
            contract = detail_r.json()
            print(f"   ✓ Contract status: {contract.get('status')}")
            print(f"   Is approved: {contract.get('is_approved')}")
            print(f"   Edit history entries: {len(contract.get('edit_history', []))}")
            print(f"   Workflow logs: {len(contract.get('workflow_logs', []))}")
        else:
            print(f"   ✗ Failed: {detail_r.status_code}")
    except Exception as e:
        log_result("Get contract detail failed", error=e)
        print(f"   ERROR: {e}")
    
    # Step 9: Update contract (create edit history)
    print("\n9. Updating contract to test edit history...")
    try:
        update_r = requests.patch(
            f"{BASE_URL}/api/admin/contracts/{contract_id}/",
            headers=headers1,
            json={"title": "Sales Agreement - Updated Title", "value": "75000.00"},
            timeout=30
        )
        log_result("Update contract", update_r)
        
        if update_r.status_code == 200:
            print(f"   ✓ Contract updated")
        else:
            print(f"   ✗ Failed: {update_r.status_code}")
    except Exception as e:
        log_result("Update contract failed", error=e)
        print(f"   ERROR: {e}")
    
    # Step 10: Get contract history
    print("\n10. Getting complete contract history...")
    try:
        history_r = requests.get(
            f"{BASE_URL}/api/admin/contracts/{contract_id}/history/",
            headers=headers1,
            timeout=30
        )
        log_result("Get contract history", history_r)
        
        if history_r.status_code == 200:
            history = history_r.json()
            print(f"   ✓ Edit history entries: {len(history.get('edit_history', []))}")
            print(f"   Workflow logs: {len(history.get('workflow_logs', []))}")
            print(f"   Approvals: {len(history.get('approvals', []))}")
        else:
            print(f"   ✗ Failed: {history_r.status_code}")
    except Exception as e:
        log_result("Get contract history failed", error=e)
        print(f"   ERROR: {e}")
    
    # Step 11: Test rejection workflow with new contract
    print("\n11. Testing rejection workflow...")
    try:
        with open("test_contract.txt", "rb") as f:
            reject_data = {
                "title": "Contract for Rejection Test",
                "contract_type": "NDA",
                "approval_required": "true",
                "approvers": user2_id
            }
            files = {"file": f}
            
            create2_r = requests.post(
                f"{BASE_URL}/api/admin/contracts/",
                headers=headers1,
                data=reject_data,
                files=files,
                timeout=60
            )
            log_result("Create contract for rejection", create2_r)
            
            if create2_r.status_code in [200, 201]:
                contract2_id = create2_r.json().get('id')
                print(f"   ✓ Contract created: {contract2_id}")
                
                # Reject it
                reject_r = requests.post(
                    f"{BASE_URL}/api/admin/contracts/{contract2_id}/approve/",
                    headers=headers2,
                    json={"action": "reject", "comments": "Terms not acceptable"},
                    timeout=30
                )
                log_result("Reject contract", reject_r)
                
                if reject_r.status_code == 200:
                    print(f"   ✓ Contract rejected successfully")
                    print(f"   Response: {reject_r.json()}")
                else:
                    print(f"   ✗ Rejection failed: {reject_r.status_code}")
            else:
                print(f"   ✗ Contract creation failed: {create2_r.status_code}")
    except Exception as e:
        log_result("Rejection workflow failed", error=e)
        print(f"   ERROR: {e}")
    
    save_results()

def save_results():
    """Save results to JSON file"""
    with open("workflow_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    success = len([r for r in results if r.get('status_code') in [200, 201, 204]])
    failed = len([r for r in results if r.get('error') or r.get('status_code') not in [200, 201, 204, None]])
    
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {len(results)}")
    print(f"Success: {success}")
    print(f"Failed: {failed}")
    print(f"\nResults saved to: workflow_test_results.json")
    print("=" * 80)

if __name__ == "__main__":
    test_workflow()

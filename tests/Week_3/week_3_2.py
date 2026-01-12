import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clm_backend.settings')
django.setup()

from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from authentication.models import User
from tenants.models import TenantModel
from contracts.models import Contract
from search.models import SearchIndexModel
from django.contrib.auth import get_user_model

def create_test_user_and_token():
    """Create test user and get JWT token"""
    try:
        # Get existing user
        user = User.objects.filter(email='test@example.com').first()
        if not user:
            user = User.objects.create_user(
                email='test@example.com',
                password='testpass123'
            )
        
        # Generate token
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        return user, access_token
    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        return None, None

def test_api_endpoints():
    """Test all API endpoints"""
    print("\n" + "="*70)
    print("🧪 API ENDPOINT TESTS")
    print("="*70)
    
    # Get user and token
    user, token = create_test_user_and_token()
    if not user:
        print("❌ Failed to create test user")
        return False
    
    # Create client
    client = APIClient()
    headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
    
    # Get tenant
    tenant = TenantModel.objects.first()
    if not tenant:
        print("❌ No tenant found")
        return False
    
    print(f"\n📋 Test Setup:")
    print(f"  • User: {user.email}")
    print(f"  • Tenant: {tenant.name}")
    print(f"  • Token: {token[:20]}...")
    
    endpoints = [
        {
            'name': 'Full-Text Search',
            'method': 'GET',
            'path': '/api/search/?q=service',
            'data': None,
        },
        {
            'name': 'Semantic Search',
            'method': 'GET',
            'path': '/api/search/semantic/?q=agreement',
            'data': None,
        },
        {
            'name': 'Hybrid Search',
            'method': 'POST',
            'path': '/api/search/hybrid/',
            'data': {'query': 'contract'},
        },
        {
            'name': 'Advanced Search',
            'method': 'POST',
            'path': '/api/search/advanced/',
            'data': {
                'query': 'payment',
                'filters': {'keywords': ['payment']}
            },
        },
        {
            'name': 'Facets',
            'method': 'GET',
            'path': '/api/search/facets/',
            'data': None,
        },
        {
            'name': 'Faceted Search',
            'method': 'POST',
            'path': '/api/search/faceted/',
            'data': {'facets': {'entity_types': ['contract']}},
        },
        {
            'name': 'Suggestions',
            'method': 'GET',
            'path': '/api/search/suggestions/?q=ser',
            'data': None,
        },
        {
            'name': 'Index Creation',
            'method': 'POST',
            'path': '/api/search/index/',
            'data': {
                'entity_type': 'contract',
                'entity_id': '00000000-0000-0000-0000-000000000001',
                'title': 'Test Contract',
                'content': 'This is a test contract',
                'keywords': ['test']
            },
        },
        {
            'name': 'Analytics',
            'method': 'GET',
            'path': '/api/search/analytics/',
            'data': None,
        },
    ]
    
    print(f"\n" + "="*70)
    print("🔍 TESTING ENDPOINTS")
    print("="*70)
    
    results = {}
    for endpoint in endpoints:
        try:
            print(f"\n{endpoint['name']}:")
            print(f"  {endpoint['method']} {endpoint['path']}")
            
            if endpoint['method'] == 'GET':
                response = client.get(endpoint['path'], **headers)
            elif endpoint['method'] == 'POST':
                response = client.post(
                    endpoint['path'],
                    data=json.dumps(endpoint['data']),
                    content_type='application/json',
                    **headers
                )
            
            status = response.status_code
            status_text = "✅" if 200 <= status < 300 else "⚠️ " if 400 <= status < 500 else "❌"
            
            print(f"  Status: {status_text} {status}")
            
            # Try to parse response
            try:
                data = response.json()
                if isinstance(data, dict):
                    if 'results' in data:
                        print(f"  Results: {len(data['results'])} items")
                    elif 'data' in data:
                        print(f"  Data: Available")
                    elif 'count' in data:
                        print(f"  Count: {data['count']}")
                    else:
                        print(f"  Response: {str(data)[:100]}")
            except:
                print(f"  Response: {str(response.content)[:100]}")
            
            results[endpoint['name']] = status
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            results[endpoint['name']] = 'ERROR'
    
    # Summary
    print(f"\n" + "="*70)
    print("📊 ENDPOINT TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if isinstance(v, int) and 200 <= v < 300)
    total = len(results)
    
    for endpoint_name, status in results.items():
        if isinstance(status, int):
            status_text = "✅ PASS" if 200 <= status < 300 else "⚠️ WARN" if 400 <= status < 500 else "❌ FAIL"
            print(f"{status_text} ({status:3d}) - {endpoint_name}")
        else:
            print(f"❌ ERROR - {endpoint_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} successful")
    
    if passed >= (total * 0.7):
        print("\n✅ MOST ENDPOINTS WORKING!")
        return True
    else:
        print("\n⚠️  Some endpoints need attention")
        return False

def main():
    """Run all endpoint tests"""
    print("\n" + "="*70)
    print("🌐 SEARCH API ENDPOINT TESTING")
    print("="*70)
    
    success = test_api_endpoints()
    
    print("\n" + "="*70)
    print("✅ ENDPOINT TESTING COMPLETE" if success else "⚠️  ENDPOINT TESTING COMPLETE")
    print("="*70 + "\n")
    
    return success

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

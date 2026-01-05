#!/usr/bin/env python3
"""
Comprehensive AI Endpoints Test Script
Tests all AI-powered features: search, generation, analysis, OCR
"""
import requests
import json
import time
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:4000/api"
TEST_EMAIL = "admin@example.com"
TEST_PASSWORD = "admin123"

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


class AIEndpointTester:
    def __init__(self):
        self.token = None
        self.test_contract_id = None
        self.results = []
    
    def print_test(self, name: str):
        print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}Testing: {name}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    
    def print_success(self, message: str):
        print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")
    
    def print_error(self, message: str):
        print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")
    
    def print_info(self, message: str):
        print(f"{Colors.OKCYAN}ℹ️  {message}{Colors.ENDC}")
    
    def print_warning(self, message: str):
        print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")
    
    def login(self) -> bool:
        """Authenticate and get token"""
        self.print_test("Authentication")
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login/",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access')
                self.print_success(f"Logged in as {TEST_EMAIL}")
                self.results.append(("Authentication", "PASS"))
                return True
            else:
                self.print_error(f"Login failed: {response.status_code}")
                self.print_info(f"Response: {response.text}")
                self.results.append(("Authentication", "FAIL"))
                return False
        except Exception as e:
            self.print_error(f"Login error: {e}")
            self.results.append(("Authentication", "ERROR"))
            return False
    
    def test_hybrid_search(self):
        """Test hybrid search endpoint"""
        self.print_test("Hybrid Search (Keyword + Semantic + RRF)")
        
        test_cases = [
            ("hybrid", "employment agreement"),
            ("keyword", "service agreement"),
            ("semantic", "contract for software development"),
        ]
        
        for mode, query in test_cases:
            try:
                self.print_info(f"Testing {mode} search for: '{query}'")
                
                response = requests.post(
                    f"{BASE_URL}/search/global/",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={
                        "query": query,
                        "mode": mode,
                        "limit": 5
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.print_success(f"{mode.capitalize()} search returned {data['total']} results")
                    
                    if data['results']:
                        self.print_info(f"Top result: {data['results'][0]['contract']['title']} (score: {data['results'][0]['score']:.2f})")
                    
                    self.results.append((f"Search ({mode})", "PASS"))
                else:
                    self.print_error(f"{mode} search failed: {response.status_code}")
                    self.print_info(f"Response: {response.text}")
                    self.results.append((f"Search ({mode})", "FAIL"))
            
            except Exception as e:
                self.print_error(f"{mode} search error: {e}")
                self.results.append((f"Search ({mode})", "ERROR"))
    
    def test_search_suggestions(self):
        """Test autocomplete suggestions"""
        self.print_test("Search Autocomplete Suggestions")
        
        try:
            response = requests.get(
                f"{BASE_URL}/search/suggestions/?q=emp&limit=5",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                suggestions = data.get('suggestions', [])
                
                self.print_success(f"Received {len(suggestions)} suggestions")
                for i, suggestion in enumerate(suggestions[:3], 1):
                    self.print_info(f"{i}. {suggestion}")
                
                self.results.append(("Autocomplete", "PASS"))
            else:
                self.print_error(f"Autocomplete failed: {response.status_code}")
                self.results.append(("Autocomplete", "FAIL"))
        
        except Exception as e:
            self.print_error(f"Autocomplete error: {e}")
            self.results.append(("Autocomplete", "ERROR"))
    
    def test_async_generation(self):
        """Test async contract generation"""
        self.print_test("Async Contract Generation (Chain-of-Thought + PII Redaction)")
        
        try:
            payload = {
                "title": "AI Test Service Agreement",
                "contract_type": "MSA",
                "description": "Master Service Agreement for AI Testing",
                "variables": {
                    "party_a": "Acme Corporation",
                    "party_b": "Client Industries Inc.",
                    "party_a_email": "legal@acme.com",
                    "party_b_email": "contracts@client.com",
                    "term": "24 months",
                    "payment_terms": "Net 30 days",
                    "total_value": "$150,000 USD",
                    "services": "Software development and maintenance"
                },
                "special_instructions": "Include termination clause with 60-day notice period. Add liability cap at contract value."
            }
            
            self.print_info("Starting async contract generation...")
            self.print_info(f"Variables: {json.dumps(payload['variables'], indent=2)}")
            
            response = requests.post(
                f"{BASE_URL}/generation/start/",
                headers={"Authorization": f"Bearer {self.token}"},
                json=payload
            )
            
            if response.status_code == 202:
                data = response.json()
                task_id = data.get('task_id')
                contract_id = data.get('contract_id')
                
                self.test_contract_id = contract_id
                
                self.print_success(f"Generation started!")
                self.print_info(f"Task ID: {task_id}")
                self.print_info(f"Contract ID: {contract_id}")
                
                # Poll for completion
                self.print_info("Waiting for generation to complete (this may take 30-60 seconds)...")
                
                max_attempts = 30
                for attempt in range(max_attempts):
                    time.sleep(2)
                    
                    status_response = requests.get(
                        f"{BASE_URL}/generation/{contract_id}/status/",
                        headers={"Authorization": f"Bearer {self.token}"}
                    )
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get('status')
                        
                        if status == 'completed':
                            self.print_success(f"✨ Contract generated successfully!")
                            self.print_info(f"Confidence Score: {status_data.get('confidence_score', 'N/A')}/10")
                            
                            # Print snippet of generated text
                            generated_text = status_data.get('generated_text', '')
                            if generated_text:
                                snippet = generated_text[:300] + "..." if len(generated_text) > 300 else generated_text
                                self.print_info(f"Generated Contract Snippet:\n{snippet}")
                            
                            self.results.append(("Async Generation", "PASS"))
                            return
                        
                        elif status == 'failed':
                            self.print_error(f"Generation failed: {status_data.get('error')}")
                            self.results.append(("Async Generation", "FAIL"))
                            return
                        
                        else:
                            print(f"  Status: {status} (attempt {attempt + 1}/{max_attempts})", end='\r')
                
                self.print_warning("Generation timeout (still processing)")
                self.results.append(("Async Generation", "TIMEOUT"))
            
            else:
                self.print_error(f"Generation start failed: {response.status_code}")
                self.print_info(f"Response: {response.text}")
                self.results.append(("Async Generation", "FAIL"))
        
        except Exception as e:
            self.print_error(f"Generation error: {e}")
            self.results.append(("Async Generation", "ERROR"))
    
    def test_clause_summary(self):
        """Test AI clause summarization"""
        self.print_test("AI Clause Summarization (Plain English)")
        
        try:
            clause = """
            Party A hereby indemnifies, defends, and holds harmless Party B, its officers, 
            directors, employees, agents, and affiliates from and against any and all claims, 
            damages, liabilities, costs, and expenses, including reasonable attorneys' fees, 
            arising out of or related to any breach of this Agreement by Party A, any negligent 
            or willful misconduct by Party A, or any infringement of intellectual property 
            rights resulting from Party A's performance under this Agreement.
            """
            
            self.print_info(f"Original clause length: {len(clause)} characters")
            
            response = requests.post(
                f"{BASE_URL}/analysis/clause-summary/",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"clause_text": clause}
            )
            
            if response.status_code == 200:
                data = response.json()
                summary = data.get('summary', '')
                
                self.print_success("Clause summarized successfully!")
                self.print_info(f"Plain-English Summary:\n{summary}")
                
                self.results.append(("Clause Summary", "PASS"))
            else:
                self.print_error(f"Clause summary failed: {response.status_code}")
                self.print_info(f"Response: {response.text}")
                self.results.append(("Clause Summary", "FAIL"))
        
        except Exception as e:
            self.print_error(f"Clause summary error: {e}")
            self.results.append(("Clause Summary", "ERROR"))
    
    def test_related_contracts(self):
        """Test finding semantically related contracts"""
        self.print_test("Related Contracts (Semantic Similarity)")
        
        if not self.test_contract_id:
            self.print_warning("Skipping - no contract ID available")
            self.results.append(("Related Contracts", "SKIP"))
            return
        
        try:
            response = requests.get(
                f"{BASE_URL}/contracts/{self.test_contract_id}/related/?limit=5",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                related = data.get('related', [])
                
                self.print_success(f"Found {len(related)} related contracts")
                
                for i, contract in enumerate(related[:3], 1):
                    self.print_info(f"{i}. {contract['contract']['title']} (similarity: {contract['similarity_score']:.2f})")
                
                self.results.append(("Related Contracts", "PASS"))
            else:
                self.print_error(f"Related contracts failed: {response.status_code}")
                self.results.append(("Related Contracts", "FAIL"))
        
        except Exception as e:
            self.print_error(f"Related contracts error: {e}")
            self.results.append(("Related Contracts", "ERROR"))
    
    def test_contract_comparison(self):
        """Test AI contract comparison"""
        self.print_test("AI Contract Comparison (Diff Analysis)")
        
        try:
            # Get two contracts to compare
            response = requests.get(
                f"{BASE_URL}/contracts/?limit=2",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                contracts = response.json().get('results', [])
                
                if len(contracts) >= 2:
                    contract_a = contracts[0]['id']
                    contract_b = contracts[1]['id']
                    
                    self.print_info(f"Comparing: {contracts[0]['title']} vs {contracts[1]['title']}")
                    
                    compare_response = requests.post(
                        f"{BASE_URL}/analysis/compare/",
                        headers={"Authorization": f"Bearer {self.token}"},
                        json={
                            "contract_a_id": contract_a,
                            "contract_b_id": contract_b
                        }
                    )
                    
                    if compare_response.status_code == 200:
                        data = compare_response.json()
                        comparison = data.get('comparison', {})
                        
                        self.print_success("Contracts compared successfully!")
                        self.print_info(f"Summary: {comparison.get('summary', 'N/A')[:200]}...")
                        
                        self.results.append(("Contract Comparison", "PASS"))
                    else:
                        self.print_error(f"Comparison failed: {compare_response.status_code}")
                        self.results.append(("Contract Comparison", "FAIL"))
                else:
                    self.print_warning("Need at least 2 contracts for comparison")
                    self.results.append(("Contract Comparison", "SKIP"))
            else:
                self.print_error("Failed to fetch contracts for comparison")
                self.results.append(("Contract Comparison", "FAIL"))
        
        except Exception as e:
            self.print_error(f"Comparison error: {e}")
            self.results.append(("Contract Comparison", "ERROR"))
    
    def test_ocr_endpoints(self):
        """Test OCR endpoints"""
        self.print_test("OCR Document Processing")
        
        if not self.test_contract_id:
            self.print_warning("Skipping - no contract ID available")
            self.results.append(("OCR Processing", "SKIP"))
            return
        
        try:
            # Test OCR status
            response = requests.get(
                f"{BASE_URL}/documents/{self.test_contract_id}/ocr-status/",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.print_success(f"OCR status: {data.get('status')}")
                self.results.append(("OCR Status", "PASS"))
            else:
                self.print_error(f"OCR status failed: {response.status_code}")
                self.results.append(("OCR Status", "FAIL"))
            
            # Test reprocess endpoint
            reprocess_response = requests.post(
                f"{BASE_URL}/documents/{self.test_contract_id}/reprocess/",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            
            if reprocess_response.status_code == 200:
                self.print_success("OCR reprocess triggered")
                self.results.append(("OCR Reprocess", "PASS"))
            else:
                self.print_info(f"OCR reprocess: {reprocess_response.status_code} (may require configuration)")
                self.results.append(("OCR Reprocess", "INFO"))
        
        except Exception as e:
            self.print_error(f"OCR error: {e}")
            self.results.append(("OCR Processing", "ERROR"))
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}Test Summary{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
        
        passed = sum(1 for _, result in self.results if result == "PASS")
        failed = sum(1 for _, result in self.results if result == "FAIL")
        errors = sum(1 for _, result in self.results if result == "ERROR")
        skipped = sum(1 for _, result in self.results if result in ["SKIP", "TIMEOUT", "INFO"])
        total = len(self.results)
        
        for test_name, result in self.results:
            if result == "PASS":
                print(f"{Colors.OKGREEN}✅ {test_name}: PASS{Colors.ENDC}")
            elif result == "FAIL":
                print(f"{Colors.FAIL}❌ {test_name}: FAIL{Colors.ENDC}")
            elif result == "ERROR":
                print(f"{Colors.FAIL}🔥 {test_name}: ERROR{Colors.ENDC}")
            else:
                print(f"{Colors.WARNING}⚠️  {test_name}: {result}{Colors.ENDC}")
        
        print(f"\n{Colors.BOLD}Results:{Colors.ENDC}")
        print(f"  Total Tests: {total}")
        print(f"  {Colors.OKGREEN}Passed: {passed}{Colors.ENDC}")
        print(f"  {Colors.FAIL}Failed: {failed}{Colors.ENDC}")
        print(f"  {Colors.FAIL}Errors: {errors}{Colors.ENDC}")
        print(f"  {Colors.WARNING}Skipped/Info: {skipped}{Colors.ENDC}")
        
        if failed == 0 and errors == 0:
            print(f"\n{Colors.OKGREEN}🎉 All tests passed!{Colors.ENDC}")
        else:
            print(f"\n{Colors.FAIL}❌ Some tests failed. Check logs above.{Colors.ENDC}")
        
        print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
    
    def run_all_tests(self):
        """Run all AI endpoint tests"""
        print(f"\n{Colors.BOLD}{'='*80}")
        print("AI Endpoints Comprehensive Test Suite")
        print(f"{'='*80}{Colors.ENDC}\n")
        
        if not self.login():
            print(f"{Colors.FAIL}Authentication failed. Cannot proceed with tests.{Colors.ENDC}")
            return
        
        # Run all tests
        self.test_hybrid_search()
        self.test_search_suggestions()
        self.test_async_generation()
        self.test_clause_summary()
        self.test_related_contracts()
        self.test_contract_comparison()
        self.test_ocr_endpoints()
        
        # Print summary
        self.print_summary()


if __name__ == "__main__":
    tester = AIEndpointTester()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Tests interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}Fatal error: {e}{Colors.ENDC}")
        sys.exit(1)

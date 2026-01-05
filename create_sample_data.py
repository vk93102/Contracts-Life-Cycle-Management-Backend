#!/usr/bin/env python
"""
Create sample contracts with REAL embeddings for testing
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SECRET_KEY', 'django-insecure-dev-key-12345')
os.environ.setdefault('DATABASE_URL', os.getenv('DATABASE_URL', ''))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clm_backend.settings')
django.setup()

from contracts.models import Contract
from authentication.models import User
from contracts.ai_services import GeminiService
import uuid

# Initialize Gemini service
gemini_service = GeminiService()

print("🚀 Creating sample contracts with REAL embeddings...\n")

# Get admin user
try:
    admin_user = User.objects.get(email='admin@example.com')
    print(f"✅ Found admin user: {admin_user.email}")
except User.DoesNotExist:
    print("❌ Admin user not found. Run: python manage.py createsuperuser")
    sys.exit(1)

# Sample contracts with REAL content
sample_contracts = [
    {
        'title': 'Software Development Master Service Agreement',
        'description': 'Comprehensive MSA for custom software development services including mobile and web applications',
        'contract_type': 'MSA',
        'counterparty': 'TechCorp Solutions Inc',
        'value': 250000.00,
        'status': 'active',
        'content': '''
        MASTER SERVICE AGREEMENT
        
        This Master Service Agreement ("Agreement") is entered into as of January 1, 2024, 
        between Acme Corporation ("Client") and TechCorp Solutions Inc ("Service Provider").
        
        1. SCOPE OF SERVICES
        Service Provider agrees to provide custom software development services including:
        - Web application development
        - Mobile application development  
        - API integration services
        - Quality assurance and testing
        
        2. PAYMENT TERMS
        Total contract value: $250,000 USD
        Payment schedule: Net 30 days from invoice date
        Late payment interest: 1.5% per month
        
        3. INTELLECTUAL PROPERTY
        All work product developed under this Agreement shall be owned by Client.
        Service Provider assigns all rights, title, and interest to Client upon full payment.
        
        4. CONFIDENTIALITY
        Both parties agree to maintain confidentiality of proprietary information.
        Non-disclosure period: 5 years from termination date.
        
        5. TERM AND TERMINATION
        Initial term: 24 months
        Renewal: Automatic 12-month renewals unless terminated with 90 days notice
        Termination for cause: Immediate upon material breach
        '''
    },
    {
        'title': 'Mutual Non-Disclosure Agreement',
        'description': 'Bilateral confidentiality agreement for business partnership discussions',
        'contract_type': 'NDA',
        'counterparty': 'Strategic Partners LLC',
        'status': 'active',
        'content': '''
        MUTUAL NON-DISCLOSURE AGREEMENT
        
        This Mutual Non-Disclosure Agreement ("Agreement") is made effective as of February 15, 2024,
        between Acme Corporation and Strategic Partners LLC (collectively the "Parties").
        
        WHEREAS, the Parties wish to explore a business partnership and will exchange confidential information.
        
        1. DEFINITION OF CONFIDENTIAL INFORMATION
        Confidential Information includes all technical, business, and financial information
        disclosed by either party including but not limited to:
        - Trade secrets and proprietary processes
        - Customer lists and business strategies
        - Financial projections and pricing information
        - Software code and technical specifications
        
        2. OBLIGATIONS
        Each Party agrees to:
        - Maintain strict confidentiality
        - Use information solely for evaluation purposes
        - Not disclose to third parties without written consent
        - Return or destroy information upon request
        
        3. EXCLUSIONS
        Information is not confidential if it:
        - Was publicly known before disclosure
        - Becomes publicly known through no breach
        - Was already in receiving party's possession
        - Is independently developed without use of confidential information
        
        4. TERM
        This Agreement shall remain in effect for 3 years from the effective date.
        Confidentiality obligations survive termination for 5 years.
        '''
    },
    {
        'title': 'Employment Agreement - Senior Software Engineer',
        'description': 'Full-time employment contract for senior software engineering position',
        'contract_type': 'Employment',
        'counterparty': 'John Smith',
        'value': 150000.00,
        'status': 'executed',
        'content': '''
        EMPLOYMENT AGREEMENT
        
        This Employment Agreement is made as of March 1, 2024, between
        Acme Corporation ("Employer") and John Smith ("Employee").
        
        1. POSITION
        Title: Senior Software Engineer
        Department: Engineering
        Reports to: VP of Engineering
        Location: San Francisco, CA (Hybrid - 3 days/week in office)
        
        2. COMPENSATION
        Base Salary: $150,000 per year, payable bi-weekly
        Bonus: Performance bonus up to 20% of base salary
        Equity: 10,000 stock options vesting over 4 years
        
        3. BENEFITS
        - Health insurance (medical, dental, vision)
        - 401(k) with 4% employer match
        - 20 days PTO per year
        - Professional development budget: $5,000/year
        
        4. DUTIES AND RESPONSIBILITIES
        - Design and develop software applications
        - Collaborate with product and design teams
        - Conduct code reviews and mentor junior engineers
        - Participate in on-call rotation
        
        5. CONFIDENTIALITY AND IP
        Employee agrees to:
        - Maintain confidentiality of company information
        - Assign all work product IP to Employer
        - Not compete with Employer during employment
        - Return all company property upon termination
        
        6. TERMINATION
        At-will employment - either party may terminate with 2 weeks notice
        Severance: 3 months salary if terminated without cause
        '''
    },
    {
        'title': 'SaaS Subscription Agreement',
        'description': 'Enterprise SaaS license agreement with annual subscription',
        'contract_type': 'License',
        'counterparty': 'Enterprise Client Corp',
        'value': 50000.00,
        'status': 'active',
        'content': '''
        SOFTWARE AS A SERVICE AGREEMENT
        
        This SaaS Agreement is effective April 1, 2024, between
        Acme Corporation ("Provider") and Enterprise Client Corp ("Customer").
        
        1. SERVICES
        Provider grants Customer access to:
        - CLM Platform (Contract Lifecycle Management)
        - Up to 100 named users
        - 500GB storage
        - Priority support (24/7 email, business hours phone)
        
        2. FEES AND PAYMENT
        Annual Subscription Fee: $50,000
        Payment terms: Annual payment in advance
        Renewal rate: Subject to 5% annual increase
        
        3. SERVICE LEVEL AGREEMENT
        Uptime guarantee: 99.9% monthly uptime
        Support response times:
        - Critical issues: 1 hour
        - High priority: 4 hours  
        - Medium priority: 1 business day
        
        4. DATA AND SECURITY
        - Provider maintains SOC 2 Type II compliance
        - Data encrypted at rest and in transit
        - Customer retains ownership of all data
        - Provider performs daily backups
        
        5. LIMITATIONS OF LIABILITY
        Provider's total liability limited to fees paid in prior 12 months.
        No liability for indirect, consequential, or punitive damages.
        
        6. TERM
        Initial term: 12 months
        Auto-renewal unless cancelled 30 days before renewal date
        '''
    },
    {
        'title': 'Consulting Services Statement of Work',
        'description': 'SOW for strategic consulting engagement on digital transformation',
        'contract_type': 'SOW',
        'counterparty': 'Global Consulting Partners',
        'value': 75000.00,
        'status': 'active',
        'content': '''
        STATEMENT OF WORK
        
        This Statement of Work is executed May 1, 2024, under the Master Service Agreement
        dated January 15, 2023, between Acme Corporation and Global Consulting Partners.
        
        1. PROJECT SCOPE
        Digital Transformation Strategy and Implementation
        
        Deliverables:
        - Current state assessment and gap analysis
        - Digital transformation roadmap (3-year plan)
        - Technology stack recommendations
        - Change management strategy
        - Executive presentation and board report
        
        2. PROJECT TIMELINE
        Phase 1 (Weeks 1-4): Discovery and assessment
        Phase 2 (Weeks 5-8): Strategy development
        Phase 3 (Weeks 9-12): Roadmap creation and recommendations
        Total duration: 12 weeks
        
        3. FEES
        Fixed fee: $75,000
        Payment schedule:
        - 30% upon signing ($22,500)
        - 40% at Phase 2 completion ($30,000)
        - 30% upon final delivery ($22,500)
        
        4. TEAM
        Consultant will provide:
        - 1 Managing Director (strategic oversight)
        - 2 Senior Consultants (analysis and design)
        - 1 Junior Consultant (research and documentation)
        
        Client will provide:
        - Executive sponsor
        - Project manager
        - Subject matter experts (as needed)
        
        5. ASSUMPTIONS
        - Client provides timely access to stakeholders
        - Historical data available within 1 week
        - Decisions made within 5 business days
        '''
    }
]

created_count = 0

for idx, contract_data in enumerate(sample_contracts, 1):
    print(f"\n📝 Creating contract {idx}/{len(sample_contracts)}: {contract_data['title']}")
    
    # Extract content for embedding
    content = contract_data.pop('content')
    
    # Create contract
    contract = Contract.objects.create(
        tenant_id=admin_user.tenant_id,
        created_by=admin_user.user_id,
        **contract_data
    )
    
    print(f"   ✅ Contract created: ID={contract.id}")
    
    # Generate REAL embedding using Gemini
    print(f"   🤖 Generating embedding with Gemini API...")
    embedding_text = f"{contract.title} {contract.description} {content}"
    embedding = gemini_service.generate_embedding(embedding_text[:30000])
    
    if embedding:
        contract.metadata = {
            'embedding': embedding,
            'embedding_generated_at': '2024-01-05T12:00:00Z',
            'embedding_dimensions': len(embedding),
            'full_text': content,
            'has_ai_summary': True
        }
        contract.save(update_fields=['metadata'])
        print(f"   ✅ Embedding generated: {len(embedding)} dimensions")
        created_count += 1
    else:
        print(f"   ⚠️  Embedding generation failed (check Gemini API key)")
        contract.metadata = {'full_text': content}
        contract.save(update_fields=['metadata'])

print(f"\n{'='*80}")
print(f"✅ COMPLETED: Created {created_count}/{len(sample_contracts)} contracts with embeddings")
print(f"{'='*80}\n")

# Verify in database
total_contracts = Contract.objects.count()
contracts_with_embeddings = Contract.objects.exclude(metadata__embedding__isnull=True).count()

print(f"📊 Database Status:")
print(f"   Total contracts: {total_contracts}")
print(f"   With embeddings: {contracts_with_embeddings}")
print(f"\n🎉 Sample data ready for testing!")

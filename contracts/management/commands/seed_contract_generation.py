"""
Seed data for Contract Generation Part A

Creates:
- Sample templates (NDA, MSA)
- Reusable clauses with versions
- Business rules for mandatory clauses and suggestions
"""
from django.core.management.base import BaseCommand
import uuid
from contracts.models import (
    ContractTemplate, Clause, BusinessRule
)


class Command(BaseCommand):
    help = 'Seed contract generation data (templates, clauses, business rules)'

    def handle(self, *args, **options):
        # Demo tenant ID (use authentication tenant from user)
        tenant_id = uuid.UUID('550e8400-e29b-41d4-a716-446655440000')
        demo_user_id = uuid.UUID('550e8400-e29b-41d4-a716-446655440001')
        
        self.stdout.write('Creating sample clauses...')
        
        # ============================================
        # CONFIDENTIALITY CLAUSES
        # ============================================
        
        conf_basic = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='CONF-001',
            name='Basic Confidentiality Clause',
            version=1,
            contract_type='NDA',
            content='''The Receiving Party agrees to keep confidential all Confidential Information disclosed by the Disclosing Party. Confidential Information shall not be disclosed to third parties without prior written consent.

The Receiving Party shall use the Confidential Information solely for the purpose of {{purpose}}.

This obligation shall survive for a period of {{confidentiality_period}} years from the date of disclosure.''',
            status='published',
            is_mandatory=True,
            alternatives=[
                {
                    'clause_id': 'CONF-002',
                    'rationale': 'Higher value contracts require stricter confidentiality',
                    'confidence': 0.92,
                    'trigger_rules': {
                        'contract_value__gte': 5000000
                    }
                }
            ],
            tags=['confidentiality', 'nda', 'basic'],
            source_template='Standard NDA Template',
            source_template_version=1,
            created_by=demo_user_id
        )
        
        conf_strict = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='CONF-002',
            name='Strict Confidentiality Clause',
            version=1,
            contract_type='NDA',
            content='''The Receiving Party agrees to maintain in strict confidence all Confidential Information disclosed by the Disclosing Party, whether orally, in writing, electronically, or by any other means.

The Receiving Party shall:
(a) Not disclose Confidential Information to any third party without prior written consent;
(b) Use the same degree of care (but no less than reasonable care) to protect the Confidential Information as it uses for its own confidential information;
(c) Limit access to Confidential Information to employees and contractors who have a legitimate need to know;
(d) Ensure all employees and contractors sign appropriate confidentiality agreements before accessing the Confidential Information.

The obligation shall survive for a period of {{confidentiality_period}} years from the date of disclosure, and indefinitely for trade secrets.

Any breach of this clause shall result in liquidated damages of {{breach_penalty}} without prejudice to other remedies.''',
            status='published',
            is_mandatory=False,
            alternatives=[],
            tags=['confidentiality', 'nda', 'strict', 'high-value'],
            source_template='Enterprise NDA Template',
            source_template_version=2,
            created_by=demo_user_id
        )
        
        # ============================================
        # TERMINATION CLAUSES
        # ============================================
        
        term_standard = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='TERM-001',
            name='Standard Termination Clause',
            version=1,
            contract_type='MSA',
            content='''Either party may terminate this Agreement upon {{termination_notice_days}} days written notice to the other party.

Upon termination, both parties shall:
(a) Return or destroy all Confidential Information;
(b) Cease using the other party's intellectual property;
(c) Settle all outstanding payments within {{payment_settlement_days}} days.

Sections relating to confidentiality, liability, and dispute resolution shall survive termination.''',
            status='published',
            is_mandatory=True,
            alternatives=[
                {
                    'clause_id': 'TERM-002',
                    'rationale': 'Long-term contracts need specific termination for cause provisions',
                    'confidence': 0.85,
                    'trigger_rules': {
                        'contract_duration__gte': 365  # 1 year or more
                    }
                }
            ],
            tags=['termination', 'msa', 'standard'],
            created_by=demo_user_id
        )
        
        term_for_cause = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='TERM-002',
            name='Termination with Cause Provisions',
            version=1,
            contract_type='MSA',
            content='''This Agreement may be terminated:

(a) By either party for convenience upon {{termination_notice_days}} days written notice;

(b) By either party for cause immediately upon written notice if the other party:
    (i) Materially breaches any term of this Agreement and fails to cure within {{cure_period_days}} days of written notice;
    (ii) Becomes insolvent or files for bankruptcy;
    (iii) Engages in fraudulent or illegal activities;
    (iv) Violates confidentiality obligations.

Upon termination:
- All licenses granted shall immediately terminate;
- Receiving party shall return or certify destruction of Confidential Information within {{return_period_days}} days;
- Outstanding payments become immediately due;
- Sections {{surviving_sections}} shall survive termination indefinitely.

Termination shall not affect accrued rights and obligations.''',
            status='published',
            is_mandatory=False,
            alternatives=[],
            tags=['termination', 'msa', 'for-cause', 'enterprise'],
            created_by=demo_user_id
        )
        
        # ============================================
        # LIABILITY CLAUSES
        # ============================================
        
        liab_basic = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='LIAB-001',
            name='Basic Liability Limitation',
            version=1,
            contract_type='MSA',
            content='''TO THE MAXIMUM EXTENT PERMITTED BY LAW, NEITHER PARTY SHALL BE LIABLE FOR ANY INDIRECT, INCIDENTAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES ARISING OUT OF THIS AGREEMENT.

Each party's total liability shall not exceed the amount paid under this Agreement in the twelve (12) months preceding the claim, or ${{max_liability_amount}}, whichever is greater.

This limitation shall not apply to:
(a) Breaches of confidentiality;
(b) Infringement of intellectual property rights;
(c) Gross negligence or willful misconduct.''',
            status='published',
            is_mandatory=False,
            alternatives=[
                {
                    'clause_id': 'LIAB-002',
                    'rationale': 'High-value contracts require higher liability caps',
                    'confidence': 0.95,
                    'trigger_rules': {
                        'contract_value__gte': 10000000
                    }
                }
            ],
            tags=['liability', 'msa', 'limitation'],
            created_by=demo_user_id
        )
        
        liab_enterprise = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='LIAB-002',
            name='Enterprise Liability Clause',
            version=1,
            contract_type='MSA',
            content='''LIMITATION OF LIABILITY:

1. Indirect Damages: Neither party shall be liable for indirect, incidental, consequential, special, or punitive damages, including lost profits or revenue.

2. Direct Damages Cap: Each party's aggregate liability for direct damages shall not exceed:
   - For claims arising in the first year: {{year_one_cap_multiplier}}x the total fees paid
   - For claims arising thereafter: {{standard_cap_multiplier}}x the fees paid in the 12 months prior to the claim
   - Minimum cap: ${{min_liability_cap}}
   - Maximum cap: ${{max_liability_cap}}

3. Exceptions to Cap: The liability cap does not apply to:
   (a) Breaches of confidentiality obligations;
   (b) Infringement or misappropriation of intellectual property;
   (c) Gross negligence or willful misconduct;
   (d) Violations of applicable law;
   (e) Indemnification obligations under Section {{indemnity_section}}.

4. Insurance: Each party shall maintain insurance coverage of at least ${{required_insurance}} for claims covered by this Agreement.''',
            status='published',
            is_mandatory=False,
            alternatives=[],
            tags=['liability', 'msa', 'enterprise', 'high-value'],
            created_by=demo_user_id
        )
        
        # ============================================
        # PAYMENT TERMS CLAUSES
        # ============================================
        
        payment_standard = Clause.objects.create(
            tenant_id=tenant_id,
            clause_id='PAY-001',
            name='Standard Payment Terms',
            version=1,
            contract_type='MSA',
            content='''Payment Terms:

1. Fees: Client shall pay Service Provider the fees set forth in attached Statement of Work or as agreed in writing.

2. Invoicing: Service Provider shall invoice Client {{invoicing_frequency}} for services rendered.

3. Payment Due: All invoices are due within {{payment_terms_days}} days of invoice date.

4. Late Payment: Late payments shall accrue interest at the rate of {{late_fee_percentage}}% per month or the maximum rate permitted by law, whichever is less.

5. Taxes: All fees are exclusive of applicable taxes, which Client shall pay in addition to the fees.''',
            status='published',
            is_mandatory=False,
            alternatives=[],
            tags=['payment', 'msa', 'standard'],
            created_by=demo_user_id
        )
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {Clause.objects.count()} clauses'))
        
        # ============================================
        # BUSINESS RULES
        # ============================================
        
        self.stdout.write('Creating business rules...')
        
        # Rule: Confidentiality is mandatory for all NDAs
        BusinessRule.objects.create(
            tenant_id=tenant_id,
            name='Mandatory Confidentiality for NDAs',
            description='All NDA contracts must include a confidentiality clause',
            rule_type='mandatory_clause',
            contract_types=['NDA'],
            conditions={},  # Always applies for NDAs
            action={
                'type': 'require_clause',
                'clause_id': 'CONF-001',
                'message': 'Confidentiality clause is mandatory for NDA contracts'
            },
            priority=100,
            is_active=True,
            created_by=demo_user_id
        )
        
        # Rule: Termination clause mandatory for MSAs
        BusinessRule.objects.create(
            tenant_id=tenant_id,
            name='Mandatory Termination for MSAs',
            description='All MSA contracts must include a termination clause',
            rule_type='mandatory_clause',
            contract_types=['MSA'],
            conditions={},
            action={
                'type': 'require_clause',
                'clause_id': 'TERM-001',
                'message': 'Termination clause is mandatory for MSA contracts'
            },
            priority=100,
            is_active=True,
            created_by=demo_user_id
        )
        
        # Rule: High-value contracts need liability clause
        BusinessRule.objects.create(
            tenant_id=tenant_id,
            name='Liability Required for High-Value Contracts',
            description='Contracts over $1M must include liability limitation',
            rule_type='mandatory_clause',
            contract_types=['MSA'],
            conditions={
                'contract_value__gte': 1000000
            },
            action={
                'type': 'require_clause',
                'clause_id': 'LIAB-001',
                'message': 'Liability clause required for contracts over $1M'
            },
            priority=90,
            is_active=True,
            created_by=demo_user_id
        )
        
        # Rule: Payment terms for service contracts
        BusinessRule.objects.create(
            tenant_id=tenant_id,
            name='Payment Terms for Service Contracts',
            description='Service agreements must include payment terms',
            rule_type='mandatory_clause',
            contract_types=['MSA', 'Service Agreement'],
            conditions={},
            action={
                'type': 'require_clause',
                'clause_id': 'PAY-001',
                'message': 'Payment terms clause is required'
            },
            priority=80,
            is_active=True,
            created_by=demo_user_id
        )
        
        # Rule: Validation - High value without liability cap
        BusinessRule.objects.create(
            tenant_id=tenant_id,
            name='Validate Liability for High-Value',
            description='Contracts over $10M should have enterprise liability clause',
            rule_type='validation',
            contract_types=['MSA'],
            conditions={
                'contract_value__gte': 10000000
            },
            action={
                'type': 'warning',
                'message': 'Consider using enterprise liability clause (LIAB-002) for contracts over $10M'
            },
            priority=70,
            is_active=True,
            created_by=demo_user_id
        )
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {BusinessRule.objects.count()} business rules'))
        
        # ============================================
        # TEMPLATES
        # ============================================
        
        self.stdout.write('Creating contract templates...')
        
        nda_template = ContractTemplate.objects.create(
            tenant_id=tenant_id,
            name='Standard NDA',
            contract_type='NDA',
            description='Standard Non-Disclosure Agreement for general business purposes',
            version=1,
            status='published',
            r2_key='templates/nda_standard_v1.docx',
            merge_fields=[
                'counterparty', 'purpose', 'confidentiality_period', 
                'effective_date', 'governing_law', 'disclosing_party',
                'receiving_party'
            ],
            mandatory_clauses=['CONF-001'],
            business_rules={
                'min_confidentiality_period': 2,
                'max_confidentiality_period': 5,
                'default_confidentiality_period': 3
            },
            created_by=demo_user_id
        )
        
        msa_template = ContractTemplate.objects.create(
            tenant_id=tenant_id,
            name='Master Service Agreement',
            contract_type='MSA',
            description='Standard MSA for ongoing service relationships',
            version=1,
            status='published',
            r2_key='templates/msa_standard_v1.docx',
            merge_fields=[
                'counterparty', 'start_date', 'end_date', 'value',
                'termination_notice_days', 'payment_terms_days',
                'governing_law', 'service_description', 'deliverables'
            ],
            mandatory_clauses=['TERM-001'],
            business_rules={
                'min_term_months': 3,
                'default_payment_terms': 30,
                'default_termination_notice': 30
            },
            created_by=demo_user_id
        )
        
        enterprise_msa = ContractTemplate.objects.create(
            tenant_id=tenant_id,
            name='Enterprise MSA',
            contract_type='MSA',
            description='Enterprise-grade MSA for high-value strategic partnerships',
            version=1,
            status='published',
            r2_key='templates/msa_enterprise_v1.docx',
            merge_fields=[
                'counterparty', 'start_date', 'end_date', 'value',
                'termination_notice_days', 'cure_period_days',
                'payment_terms_days', 'governing_law',
                'max_liability_cap', 'required_insurance'
            ],
            mandatory_clauses=['TERM-002', 'LIAB-002', 'PAY-001'],
            business_rules={
                'min_value': 5000000,
                'required_insurance_min': 2000000,
                'default_liability_cap_multiplier': 2
            },
            created_by=demo_user_id
        )
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {ContractTemplate.objects.count()} templates'))
        
        self.stdout.write(self.style.SUCCESS('\n=== Contract Generation Seed Data Complete ==='))
        self.stdout.write(f'Clauses: {Clause.objects.count()}')
        self.stdout.write(f'Templates: {ContractTemplate.objects.count()}')
        self.stdout.write(f'Business Rules: {BusinessRule.objects.count()}')
        self.stdout.write(f'Tenant ID: {tenant_id}')

"""
Management command to seed test data for contract generation
"""
import uuid
from django.core.management.base import BaseCommand
from contracts.models import ContractTemplate, Clause


class Command(BaseCommand):
    help = 'Seed test data for contract generation'

    def handle(self, *args, **options):
        # Create test tenant ID
        tenant_id = uuid.uuid4()

        # Create NDA template
        nda_template = ContractTemplate.objects.create(
            tenant_id=tenant_id,
            name='Standard NDA Template',
            contract_type='NDA',
            description='Standard Non-Disclosure Agreement template',
            version=1,
            status='published',
            merge_fields=['contract_title', 'party_a', 'party_b', 'effective_date', 'term_months'],
            mandatory_clauses=['CONF-001', 'TERM-001', 'GOV-001'],
            business_rules={
                'required_fields': ['contract_title', 'party_a', 'party_b', 'effective_date'],
                'min_term_months': 6,
                'max_term_months': 60
            },
            created_by=uuid.uuid4()
        )

        # Create test clauses
        clauses_data = [
            {
                'clause_id': 'CONF-001',
                'name': 'Confidentiality Obligations',
                'contract_type': 'NDA',
                'content': 'The Receiving Party agrees to maintain the confidentiality of all Confidential Information disclosed by the Disclosing Party and to use such information solely for the purpose of evaluating a potential business relationship.',
                'is_mandatory': True,
                'alternatives': [
                    {
                        'clause_id': 'CONF-002',
                        'rationale': 'Broader confidentiality scope including third parties',
                        'confidence': 0.8
                    }
                ]
            },
            {
                'clause_id': 'TERM-001',
                'name': 'Term and Termination',
                'contract_type': 'NDA',
                'content': 'This Agreement shall remain in effect for a period of {term_months} months from the Effective Date, unless terminated earlier by mutual agreement or as otherwise provided herein.',
                'is_mandatory': True,
                'alternatives': []
            },
            {
                'clause_id': 'GOV-001',
                'name': 'Governing Law',
                'contract_type': 'NDA',
                'content': 'This Agreement shall be governed by and construed in accordance with the laws of the State of California, without regard to its conflict of laws principles.',
                'is_mandatory': True,
                'alternatives': []
            },
            {
                'clause_id': 'CONF-002',
                'name': 'Enhanced Confidentiality',
                'contract_type': 'NDA',
                'content': 'The Receiving Party agrees to maintain the strictest confidentiality of all Confidential Information, including information disclosed by affiliates, agents, or third parties, and to implement appropriate security measures to protect such information.',
                'is_mandatory': False,
                'alternatives': []
            }
        ]

        for clause_data in clauses_data:
            Clause.objects.create(
                tenant_id=tenant_id,
                clause_id=clause_data['clause_id'],
                name=clause_data['name'],
                version=1,
                contract_type=clause_data['contract_type'],
                content=clause_data['content'],
                status='published',
                is_mandatory=clause_data['is_mandatory'],
                alternatives=clause_data['alternatives'],
                created_by=uuid.uuid4()
            )

        self.stdout.write(
            self.style.SUCCESS(f'Seeded test data for tenant {tenant_id}')
        )
        self.stdout.write(f'Created template: {nda_template.name}')
        self.stdout.write(f'Created {len(clauses_data)} clauses')
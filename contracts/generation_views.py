"""
Contract generation and management views with Part A features:
- Template-based generation
- Clause assembly with provenance
- Alternative clause suggestions
- Business rule validation
- Mandatory clause enforcement
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
import uuid

from .models import (
    Contract, ContractVersion, ContractTemplate, Clause, 
    GenerationJob, BusinessRule, ContractClause
)
from .serializers import (
    ContractSerializer, ContractDetailSerializer,
    ContractTemplateSerializer, ClauseSerializer,
    ContractVersionSerializer, GenerationJobSerializer,
    ContractGenerateSerializer, ContractApproveSerializer
)
from .services import ContractGenerator, RuleEngine


class ContractTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for contract templates
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ContractTemplateSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        return ContractTemplate.objects.filter(
            tenant_id=tenant_id,
            status='published'
        )


class ClauseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for clauses with alternative suggestions
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ClauseSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        queryset = Clause.objects.filter(
            tenant_id=tenant_id,
            status='published'
        )
        
        # Filter by contract type if provided
        contract_type = self.request.query_params.get('contract_type')
        if contract_type:
            queryset = queryset.filter(contract_type=contract_type)
        
        return queryset
    
    @action(detail=True, methods=['post'], url_path='alternatives')
    def alternatives(self, request, pk=None):
        """
        POST /clauses/{id}/alternatives/
        Get alternative clause suggestions based on contract context
        
        Request:
        {
            "contract_type": "MSA",
            "contract_value": 5000000,
            "counterparty": "Acme Corp"
        }
        
        Response:
        {
            "alternatives": [
                {
                    "clause_id": "LIAB-002",
                    "name": "Strict Liability Clause",
                    "content": "...",
                    "rationale": "Higher value contracts require stricter liability",
                    "confidence": 0.92,
                    "source": "rule_based"
                }
            ]
        }
        """
        clause = self.get_object()
        tenant_id = self.request.user.tenant_id
        
        context = request.data
        contract_type = context.get('contract_type', 'Unknown')
        
        rule_engine = RuleEngine()
        suggestions = rule_engine.get_clause_suggestions(
            tenant_id, contract_type, context, clause.clause_id
        )
        
        suggestion_ids = [s['clause_id'] for s in suggestions]
        alt_clauses = Clause.objects.filter(
            tenant_id=tenant_id,
            clause_id__in=suggestion_ids,
            status='published'
        )
        
        clause_map = {c.clause_id: c for c in alt_clauses}
        
        result = []
        for suggestion in suggestions:
            alt_clause = clause_map.get(suggestion['clause_id'])
            if alt_clause:
                result.append({
                    **ClauseSerializer(alt_clause).data,
                    'rationale': suggestion['rationale'],
                    'confidence': suggestion['confidence'],
                    'source': suggestion['source']
                })
        
        return Response({'alternatives': result})


class ContractViewSet(viewsets.ModelViewSet):
    """
    API endpoint for contracts with generation, approval, and version management
    """
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ContractDetailSerializer
        elif self.action == 'generate':
            return ContractGenerateSerializer
        elif self.action == 'approve':
            return ContractApproveSerializer
        return ContractSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        return Contract.objects.filter(tenant_id=tenant_id)
    
    def perform_create(self, serializer):
        """Set tenant_id and created_by when creating a contract"""
        serializer.save(
            tenant_id=self.request.user.tenant_id,
            created_by=self.request.user.user_id
        )
    
    @action(detail=False, methods=['get'], url_path='statistics')
    def statistics(self, request):
        """
        GET /contracts/statistics/
        Get contract statistics for dashboard
        
        Response:
        {
            "total": 127,
            "draft": 45,
            "pending": 30,
            "approved": 40,
            "rejected": 5,
            "executed": 7,
            "monthly_trends": [
                {"month": "Jan", "approved": 12, "rejected": 2},
                ...
            ]
        }
        """
        from django.db.models import Count, Q
        from datetime import timedelta
        from django.utils import timezone
        
        tenant_id = request.user.tenant_id
        queryset = Contract.objects.filter(tenant_id=tenant_id)
        
        # Get status counts
        stats = queryset.aggregate(
            total=Count('id'),
            draft=Count('id', filter=Q(status='draft')),
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            rejected=Count('id', filter=Q(status='rejected')),
            executed=Count('id', filter=Q(status='executed'))
        )
        
        # Get monthly trends for last 6 months
        monthly_trends = []
        for i in range(5, -1, -1):
            month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30 * i)
            month_end = (month_start + timedelta(days=32)).replace(day=1)
            
            month_contracts = queryset.filter(
                created_at__gte=month_start,
                created_at__lt=month_end
            )
            
            approved_count = month_contracts.filter(status='approved').count()
            rejected_count = month_contracts.filter(status='rejected').count()
            
            monthly_trends.append({
                'month': month_start.strftime('%b'),
                'approved': approved_count,
                'rejected': rejected_count
            })
        
        return Response({
            **stats,
            'monthly_trends': monthly_trends
        })
    
    @action(detail=False, methods=['get'], url_path='recent')
    def recent(self, request):
        """
        GET /contracts/recent/?limit=10
        Get recent contracts
        """
        tenant_id = request.user.tenant_id
        limit = int(request.query_params.get('limit', 10))
        
        contracts = Contract.objects.filter(
            tenant_id=tenant_id
        ).order_by('-updated_at')[:limit]
        
        # Get user names from authentication app
        from authentication.models import User
        user_ids = list(set([str(c.created_by) for c in contracts]))
        users = User.objects.filter(user_id__in=user_ids)
        user_map = {str(u.user_id): f"{u.first_name} {u.last_name}".strip() or u.email for u in users}
        
        result = []
        for contract in contracts:
            data = ContractSerializer(contract).data
            data['created_by_name'] = user_map.get(str(contract.created_by), 'Unknown')
            result.append(data)
        
        return Response(result)
    
    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        POST /contracts/generate/
        Generate a new contract from template with clause assembly
        
        Request:
        {
            "template_id": "uuid",
            "structured_inputs": {
                "counterparty": "Acme Corp",
                "value": 5000000,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31"
            },
            "user_instructions": "Make termination stricter",
            "title": "MSA with Acme Corp",
            "selected_clauses": ["CONF-001", "TERM-001"]  # Optional
        }
        
        Response:
        {
            "contract": {...},
            "version": {...},
            "mandatory_clauses": [
                {
                    "clause_id": "CONF-001",
                    "message": "Confidentiality required for all contracts",
                    "rule_name": "Mandatory Confidentiality"
                }
            ],
            "clause_suggestions": {
                "CONF-001": [
                    {
                        "clause_id": "CONF-002",
                        "rationale": "Higher value contracts",
                        "confidence": 0.89
                    }
                ]
            },
            "validation_errors": []
        }
        """
        tenant_id = request.user.tenant_id
        user_id = request.user.user_id
        
        template_id = request.data.get('template_id')
        structured_inputs = request.data.get('structured_inputs', {})
        user_instructions = request.data.get('user_instructions')
        title = request.data.get('title')
        selected_clauses = request.data.get('selected_clauses')
        
        if not template_id:
            return Response(
                {'error': 'template_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            generator = ContractGenerator(user_id, tenant_id)
            
            # Create contract
            contract = generator.generate_from_template(
                template_id=uuid.UUID(template_id),
                structured_inputs=structured_inputs,
                user_instructions=user_instructions,
                title=title
            )
            
            # Create first version with clause assembly
            version = generator.create_version(
                contract=contract,
                selected_clauses=selected_clauses,
                change_summary='Initial draft'
            )
            
            # Get context for suggestions and validation
            context = {
                'contract_type': contract.contract_type,
                'contract_value': float(contract.value) if contract.value else 0,
                **structured_inputs
            }
            
            rule_engine = RuleEngine()
            mandatory_clauses = rule_engine.get_mandatory_clauses(
                tenant_id, contract.contract_type, context
            )
            
            # Get all clause suggestions
            clause_suggestions = {}
            for clause_id in (selected_clauses or []):
                suggestions = rule_engine.get_clause_suggestions(
                    tenant_id, contract.contract_type, context, clause_id
                )
                if suggestions:
                    clause_suggestions[clause_id] = suggestions
            
            return Response({
                'contract': ContractDetailSerializer(contract).data,
                'version': ContractVersionSerializer(version).data,
                'mandatory_clauses': mandatory_clauses,
                'clause_suggestions': clause_suggestions,
                'validation_errors': []
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        """
        GET /contracts/{id}/versions/
        Get all versions of a contract with clause provenance
        """
        contract = self.get_object()
        versions = contract.versions.all()
        serializer = ContractVersionSerializer(versions, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='create-version')
    def create_version(self, request, pk=None):
        """
        POST /contracts/{id}/create-version/
        Create a new version with different clauses
        
        Request:
        {
            "selected_clauses": ["CONF-001", "TERM-001", "LIAB-002"],
            "change_summary": "Updated liability clause to stricter version"
        }
        """
        contract = self.get_object()
        
        selected_clauses = request.data.get('selected_clauses', [])
        change_summary = request.data.get('change_summary', '')
        
        if not selected_clauses:
            return Response(
                {'error': 'selected_clauses is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            tenant_id = request.user.tenant_id
            user_id = request.user.user_id
            
            generator = ContractGenerator(user_id, tenant_id)
            version = generator.create_version(
                contract=contract,
                selected_clauses=selected_clauses,
                change_summary=change_summary
            )
            
            return Response(
                ContractVersionSerializer(version).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'], url_path='versions/(?P<version_number>[0-9]+)/clauses')
    def version_clauses(self, request, pk=None, version_number=None):
        """
        GET /contracts/{id}/versions/{version_number}/clauses/
        Get all clauses with full provenance for a specific version
        
        Response:
        {
            "clauses": [
                {
                    "clause_id": "CONF-001",
                    "clause_version": 3,
                    "name": "Confidentiality Clause",
                    "content": "...",
                    "is_mandatory": true,
                    "position": 1,
                    "alternatives_suggested": [...],
                    "provenance": {
                        "source": "template",
                        "template_id": "uuid",
                        "template_version": 5,
                        "added_at": "2026-01-01T12:00:00Z"
                    }
                }
            ]
        }
        """
        contract = self.get_object()
        version = get_object_or_404(
            ContractVersion,
            contract=contract,
            version_number=version_number
        )
        
        clauses = version.clauses.all()
        
        data = []
        for cc in clauses:
            data.append({
                'clause_id': cc.clause_id,
                'clause_version': cc.clause_version,
                'name': cc.clause_name,
                'content': cc.clause_content,
                'is_mandatory': cc.is_mandatory,
                'position': cc.position,
                'alternatives_suggested': cc.alternatives_suggested,
                'provenance': {
                    'source': 'template',
                    'template_id': str(version.template_id),
                    'template_version': version.template_version,
                    'added_at': version.created_at.isoformat(),
                    'added_by': str(version.created_by)
                }
            })
        
        return Response({'clauses': data})
    
    @action(detail=False, methods=['post'], url_path='validate-clauses')
    def validate_clauses(self, request):
        """
        POST /contracts/validate-clauses/
        Validate a set of clauses against business rules
        
        Request:
        {
            "contract_type": "MSA",
            "contract_value": 5000000,
            "selected_clauses": ["CONF-001", "TERM-001"]
        }
        
        Response:
        {
            "is_valid": false,
            "errors": ["Mandatory clause missing: LIAB-001"],
            "warnings": [],
            "mandatory_clauses": [...]
        }
        """
        tenant_id = request.user.tenant_id
        
        contract_type = request.data.get('contract_type', '')
        context = request.data
        selected_clauses = request.data.get('selected_clauses', [])
        
        rule_engine = RuleEngine()
        
        is_valid, errors = rule_engine.validate_contract(
            tenant_id, contract_type, context, selected_clauses
        )
        
        mandatory = rule_engine.get_mandatory_clauses(
            tenant_id, contract_type, context
        )
        
        return Response({
            'is_valid': is_valid,
            'errors': errors,
            'warnings': [],
            'mandatory_clauses': mandatory
        })
    
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """
        POST /contracts/{id}/approve
        Approve a contract for download/send/sign
        """
        contract = self.get_object()
        serializer = ContractApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        if not serializer.validated_data['reviewed']:
            return Response(
                {'error': 'You must review the contract before approving'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if contract.is_approved:
            return Response(
                {'error': 'Contract is already approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tenant_id = request.user.tenant_id
        user_id = request.user.user_id
        
        service = ContractGenerationService(tenant_id, user_id)
        contract = service.approve_contract(str(contract.id))
        
        return Response(
            ContractDetailSerializer(contract).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """
        GET /contracts/{id}/download
        Download the latest version (requires approval)
        """
        contract = self.get_object()
        
        if not contract.is_approved:
            return Response(
                {'error': 'Contract must be approved before download'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        latest_version = contract.versions.first()
        if not latest_version:
            return Response(
                {'error': 'No version available'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # In production: Generate presigned R2 URL and redirect
        download_url = f"https://r2.example.com/{latest_version.r2_key}"
        
        return Response({
            'download_url': download_url,
            'filename': f"{contract.title}_v{latest_version.version_number}.docx",
            'version': latest_version.version_number
        })
    
    @action(detail=True, methods=['get'], url_path='versions/(?P<version_number>[0-9]+)')
    def version_detail(self, request, pk=None, version_number=None):
        """
        GET /contracts/{id}/versions/{version_number}
        Get specific version details
        """
        contract = self.get_object()
        version = get_object_or_404(
            ContractVersion,
            contract=contract,
            version_number=version_number
        )
        serializer = ContractVersionSerializer(version)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], url_path='new-version')
    def new_version(self, request, pk=None):
        """
        POST /contracts/{id}/new-version
        Create a new version with changes
        """
        contract = self.get_object()
        
        changes = request.data.get('changes', {})
        change_summary = request.data.get('change_summary', 'Updated contract')
        
        tenant_id = request.user.tenant_id
        user_id = request.user.user_id
        
        service = ContractGenerationService(tenant_id, user_id)
        
        try:
            new_version = service.create_new_version(
                contract_id=str(contract.id),
                changes=changes,
                change_summary=change_summary
            )
            
            return Response(
                ContractVersionSerializer(new_version).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {'error': 'Failed to create new version', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GenerationJobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for tracking async generation jobs
    """
    permission_classes = [IsAuthenticated]
    serializer_class = GenerationJobSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        # Filter by user's contracts
        user_id = self.request.user.user_id
        return GenerationJob.objects.filter(
            contract__tenant_id=tenant_id,
            contract__created_by=user_id
        )

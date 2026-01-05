"""
Contract generation and management views with Part A features:
- Template-based generation
- Clause assembly with provenance
- Alternative clause suggestions
- Business rule validation
- Mandatory clause enforcement
"""
import logging
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)
import uuid
import hashlib

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
from authentication.r2_service import R2StorageService
from .workflow_services import WorkflowEngine, AuditLogService, NotificationService
from .workflow_engine import WorkflowMatchEngine, WorkflowOrchestrator
from .workflow_serializers import WorkflowStartSerializer, ContractApproveSerializer as WorkflowApproveSerializer


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
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
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
        """
        Set tenant_id and created_by when creating a contract
        
        Production-Level Feature:
        Auto-starts workflow if contract matches any active workflow rules
        Uses the WorkflowMatchEngine to dynamically evaluate trigger conditions
        """
        # 1. Save the contract
        contract = serializer.save(
            tenant_id=self.request.user.tenant_id,
            created_by=self.request.user.user_id
        )
        
        # 2. Auto-match and start workflow if applicable
        try:
            workflow = WorkflowMatchEngine.find_matching_workflow(contract)
            
            if workflow:
                # Start workflow (this will trigger signals for notifications)
                WorkflowOrchestrator.start_workflow(
                    contract=contract,
                    workflow_definition=workflow,
                    initiated_by=self.request.user.user_id,
                    metadata={
                        'auto_started': True,
                        'matched_rules': workflow.trigger_conditions
                    }
                )
                
                logger.info(
                    f"Auto-started workflow '{workflow.name}' "
                    f"for contract {contract.id}"
                )
        except Exception as e:
            # Log but don't crash contract creation
            logger.error(
                f"Failed to auto-start workflow for contract {contract.id}: {e}",
                exc_info=True
            )

    def create(self, request, *args, **kwargs):
        """Create contract.

        Supports multipart form uploads with a `file` field. If a file is provided,
        it is uploaded to Cloudflare R2 and stored as the initial ContractVersion.
        """
        uploaded_file = request.FILES.get('file')

        allowed_fields = [
            'title',
            'contract_type',
            'status',
            'value',
            'counterparty',
            'start_date',
            'end_date',
        ]
        payload = {k: request.data.get(k) for k in allowed_fields if k in request.data}

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            contract = serializer.save(
                tenant_id=request.user.tenant_id,
                created_by=request.user.user_id,
            )

            if uploaded_file:
                file_bytes = uploaded_file.read()
                try:
                    uploaded_file.seek(0)
                except Exception:
                    pass

                file_hash = hashlib.sha256(file_bytes).hexdigest()
                file_size = getattr(uploaded_file, 'size', None)

                r2_service = R2StorageService()
                r2_key = r2_service.upload_file(uploaded_file, request.user.tenant_id, uploaded_file.name)

                template_id = contract.template_id or uuid.uuid4()
                template_version = getattr(contract.template, 'version', None) or 1

                ContractVersion.objects.create(
                    contract=contract,
                    version_number=1,
                    r2_key=r2_key,
                    template_id=template_id,
                    template_version=template_version,
                    change_summary='Initial document upload',
                    created_by=request.user.user_id,
                    file_size=file_size,
                    file_hash=file_hash,
                )

                contract.current_version = 1
                contract.save(update_fields=['current_version'])

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['get'], url_path='download-url')
    def download_url(self, request, pk=None):
        """GET /contracts/{id}/download-url/

        Returns a presigned URL for the latest uploaded/generated document.
        """
        contract = self.get_object()
        try:
            latest_version = contract.versions.latest('version_number')
        except ContractVersion.DoesNotExist:
            return Response(
                {'error': 'No document available for this contract'},
                status=status.HTTP_404_NOT_FOUND
            )

        r2_service = R2StorageService()
        url = r2_service.generate_presigned_url(latest_version.r2_key)
        return Response({
            'contract_id': str(contract.id),
            'version_number': latest_version.version_number,
            'r2_key': latest_version.r2_key,
            'download_url': url,
        })
    
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
    
    @action(detail=True, methods=['post'], url_path='workflow/start')
    def start_workflow(self, request, pk=None):
        """
        POST /contracts/{id}/workflow/start/
        Start approval workflow for a contract
        
        Uses Production-Level WorkflowOrchestrator:
        - Dynamic rule matching via kwargs unpacking
        - Transaction-safe workflow creation
        - Automatic notification triggering via signals
        
        Request:
        {
            "workflow_definition_id": "uuid"  // Optional, will auto-match if not provided
        }
        """
        contract = self.get_object()
        
        if contract.status not in ['draft', 'rejected']:
            return Response(
                {'error': f'Cannot start workflow for contract in {contract.status} status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = WorkflowStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        workflow_id = serializer.validated_data.get('workflow_definition_id')
        metadata = serializer.validated_data.get('metadata', {})
        
        try:
            from .workflow_models import WorkflowDefinition
            workflow_definition = None
            
            if workflow_id:
                workflow_definition = WorkflowDefinition.objects.get(
                    id=workflow_id,
                    tenant_id=request.user.tenant_id,
                    is_active=True
                )
            
            # Use the production-level orchestrator
            workflow_instance = WorkflowOrchestrator.start_workflow(
                contract=contract,
                workflow_definition=workflow_definition,
                initiated_by=request.user.user_id,
                metadata={**metadata, 'manual_start': True}
            )
            
            from .workflow_serializers import WorkflowInstanceSerializer
            return Response(
                WorkflowInstanceSerializer(workflow_instance).data,
                status=status.HTTP_201_CREATED
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error starting workflow: {e}", exc_info=True)
            return Response(
                {'error': 'Failed to start workflow'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='workflow/status')
    def workflow_status(self, request, pk=None):
        """
        GET /contracts/{id}/workflow/status/
        Get current workflow status for a contract
        
        Response:
        {
            "contract_id": "uuid",
            "status": "pending",
            "current_stage": "Legal Review",
            "workflow_name": "High Value Contract Approval",
            "started_at": "2026-01-05T10:00:00Z",
            "pending_approvers": [
                {
                    "approver_id": "uuid",
                    "stage": "Legal Review",
                    "due_at": "2026-01-07T10:00:00Z",
                    "is_overdue": false
                }
            ]
        }
        """
        contract = self.get_object()
        
        from .workflow_models import WorkflowInstance, WorkflowStageApproval
        
        try:
            workflow = WorkflowInstance.objects.filter(
                contract=contract,
                status='active'
            ).select_related('workflow_definition').first()
            
            if not workflow:
                return Response({
                    'contract_id': str(contract.id),
                    'status': contract.status,
                    'workflow_active': False,
                    'message': 'No active workflow for this contract'
                })
            
            # Get pending approvals
            pending_approvals = WorkflowStageApproval.objects.filter(
                workflow_instance=workflow,
                status='pending'
            ).order_by('stage_sequence', 'requested_at')
            
            pending_list = []
            for approval in pending_approvals:
                pending_list.append({
                    'approval_id': str(approval.id),
                    'approver_id': str(approval.approver),
                    'stage': approval.stage_name,
                    'requested_at': approval.requested_at,
                    'due_at': approval.due_at,
                    'is_overdue': approval.is_overdue()
                })
            
            return Response({
                'contract_id': str(contract.id),
                'workflow_id': str(workflow.id),
                'status': contract.status,
                'workflow_active': True,
                'workflow_name': workflow.workflow_definition.name,
                'current_stage': workflow.current_stage_name,
                'started_at': workflow.started_at,
                'pending_approvers': pending_list
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='approve')
    def workflow_approve(self, request, pk=None):
        """
        POST /contracts/{id}/approve/
        Approve or reject contract in workflow
        
        Uses Production-Level WorkflowOrchestrator:
        - State machine validation
        - Automatic workflow advancement
        - Event-driven notifications via signals
        
        Request:
        {
            "action": "approve",  // or "reject" or "delegate"
            "comments": "Approved with minor concerns",
            "delegate_to": "uuid"  // Required if action is "delegate"
        }
        """
        contract = self.get_object()
        
        serializer = WorkflowApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action = serializer.validated_data['action']
        comments = serializer.validated_data.get('comments', '')
        delegate_to = serializer.validated_data.get('delegate_to')
        
        from .workflow_models import WorkflowStageApproval
        
        # Find pending approval for this user
        approval = WorkflowStageApproval.objects.filter(
            workflow_instance__contract=contract,
            approver=request.user.user_id,
            status='pending'
        ).select_related('workflow_instance').first()
        
        if not approval:
            return Response(
                {'error': 'No pending approval found for you on this contract'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Use the production-level orchestrator
            workflow_instance = WorkflowOrchestrator.process_approval(
                approval=approval,
                action=action,
                user_id=request.user.user_id,
                comments=comments,
                delegate_to=delegate_to
            )
            
            # Refresh contract to get updated status
            contract.refresh_from_db()
            
            from .workflow_serializers import WorkflowInstanceSerializer
            return Response({
                'message': f'Contract {action}d successfully',
                'workflow': WorkflowInstanceSerializer(workflow_instance).data,
                'contract_status': contract.status
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error processing approval: {e}", exc_info=True)
            return Response(
                {'error': 'Failed to process approval'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='reject')
    def workflow_reject(self, request, pk=None):
        """
        POST /contracts/{id}/reject/
        Reject contract (shortcut for approve with action=reject)
        """
        request.data['action'] = 'reject'
        return self.workflow_approve(request, pk)
    
    @action(detail=True, methods=['post'], url_path='delegate')
    def workflow_delegate(self, request, pk=None):
        """
        POST /contracts/{id}/delegate/
        Delegate approval to another user
        
        Request:
        {
            "delegate_to": "uuid",
            "comments": "Delegating to team lead"
        }
        """
        request.data['action'] = 'delegate'
        return self.workflow_approve(request, pk)
    
    @action(detail=True, methods=['get'], url_path='audit')
    def audit_trail(self, request, pk=None):
        """
        GET /contracts/{id}/audit/
        Get full audit trail for a contract
        
        Response: List of all actions performed on the contract with timestamps
        """
        contract = self.get_object()
        
        from .workflow_models import AuditLog
        
        logs = AuditLog.objects.filter(
            contract=contract
        ).order_by('-timestamp')
        
        from .workflow_serializers import AuditLogSerializer
        serializer = AuditLogSerializer(logs, many=True)
        
        return Response({
            'contract_id': str(contract.id),
            'contract_title': contract.title,
            'total_events': logs.count(),
            'audit_trail': serializer.data
        })
    
    @action(detail=False, methods=['post'], url_path='validate-clauses')
    def validate_clauses(self, request):
        """
        POST /contracts/validate-clauses/
        Validate clause selection against business rules
        
        Request:
        {
            "clauses": ["CONF-001", "TERM-001"],
            "context": {
                "contract_type": "MSA",
                "contract_value": 5000000
            }
        }
        
        Response:
        {
            "is_valid": true,
            "errors": [],
            "warnings": [],
            "mandatory_clauses": [
                {
                    "clause_id": "LIAB-001",
                    "message": "Liability clause required for high-value contracts"
                }
            ]
        }
        """
        clauses = request.data.get('clauses', [])
        context = request.data.get('context', {})
        
        tenant_id = request.user.tenant_id
        contract_type = context.get('contract_type', 'General')
        
        rule_engine = RuleEngine()
        
        # Get mandatory clauses
        mandatory_clauses = rule_engine.get_mandatory_clauses(
            tenant_id, contract_type, context
        )
        
        # Check for missing mandatory clauses
        mandatory_ids = [m['clause_id'] for m in mandatory_clauses]
        missing_mandatory = [mid for mid in mandatory_ids if mid not in clauses]
        
        errors = []
        warnings = []
        
        if missing_mandatory:
            for clause_id in missing_mandatory:
                clause_info = next((m for m in mandatory_clauses if m['clause_id'] == clause_id), None)
                if clause_info:
                    errors.append({
                        'type': 'missing_mandatory_clause',
                        'clause_id': clause_id,
                        'message': clause_info.get('message', f'Clause {clause_id} is mandatory')
                    })
        
        return Response({
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'mandatory_clauses': mandatory_clauses
        })
    
    @action(detail=True, methods=['post'], url_path='apply-template')
    def apply_template(self, request, pk=None):
        """
        POST /contracts/{id}/apply-template/
        Apply a template to an existing contract
        
        Request:
        {
            "template_id": "uuid"
        }
        """
        contract = self.get_object()
        template_id = request.data.get('template_id')
        
        if not template_id:
            return Response(
                {'error': 'template_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            template = ContractTemplate.objects.get(
                id=template_id,
                tenant_id=request.user.tenant_id,
                status='published'
            )
            
            contract.template = template
            contract.contract_type = template.contract_type
            contract.save(update_fields=['template', 'contract_type', 'updated_at'])
            
            # Log audit event
            AuditLogService.log(
                tenant_id=request.user.tenant_id,
                user_id=request.user.user_id,
                action='contract_updated',
                resource_type='contract',
                resource_id=contract.id,
                contract=contract,
                metadata={'action': 'template_applied', 'template_id': str(template_id)}
            )
            
            return Response(
                ContractDetailSerializer(contract).data,
                status=status.HTTP_200_OK
            )
        except ContractTemplate.DoesNotExist:
            return Response(
                {'error': 'Template not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], url_path='approve-old')
    def approve_old(self, request, pk=None):
        """
        POST /contracts/{id}/approve-old
        Approve a contract for download/send/sign (legacy endpoint)
        """
        contract = self.get_object()
        serializer = ContractApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Auto-set reviewed to True if not provided
        reviewed = serializer.validated_data.get('reviewed', True)
        
        if not reviewed:
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

    @action(detail=True, methods=['get'], url_path='related')
    def related_contracts(self, request, pk=None):
        """
        Find semantically related contracts
        
        URL: GET /api/contracts/{id}/related/
        
        Query Params:
        - limit: Max results (default 5)
        
        Response:
        {
            "related": [
                {
                    "id": "uuid",
                    "title": "...",
                    "similarity_score": 0.92,
                    "contract": {...}
                }
            ]
        }
        """
        from .search_services import hybrid_search_service
        from .serializers import ContractSerializer
        
        tenant_id = str(request.user.tenant_id)
        limit = int(request.query_params.get('limit', 5))
        
        try:
            contract = self.get_object()
            
            # Check if this contract has an embedding yet
            if not contract.metadata or not contract.metadata.get('embedding'):
                return Response(
                    {
                        'message': 'This contract is still processing its embedding.',
                        'status': 'processing',
                        'related': []
                    },
                    status=status.HTTP_202_ACCEPTED
                )
            
            # Find similar contracts
            similar = hybrid_search_service.find_similar_contracts(
                contract_id=str(contract.id),
                tenant_id=tenant_id,
                limit=limit
            )
            
            # Enrich with full data
            enriched = []
            for item in similar:
                try:
                    related_contract = Contract.objects.get(id=item['id'], tenant_id=tenant_id)
                    enriched.append({
                        'id': item['id'],
                        'similarity_score': item.get('similarity_score', 0),
                        'contract': ContractSerializer(related_contract).data
                    })
                except Contract.DoesNotExist:
                    continue
            
            return Response({
                'source_contract': {
                    'id': str(contract.id),
                    'title': contract.title
                },
                'related': enriched
            })
            
        except Exception as e:
            logger.error(f"Related contracts search failed: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
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

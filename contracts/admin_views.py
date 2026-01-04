"""
Admin API Views for Contract Management Dashboard
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Count

from .models import (
    Contract, ContractApproval, ContractEditHistory, 
    WorkflowLog, ContractTemplate, Clause
)
from .serializers import (
    ContractSerializer, ContractDetailWithWorkflowSerializer,
    ContractApprovalSerializer, ContractEditHistorySerializer,
    WorkflowLogSerializer, ApprovalActionSerializer,
    ContractTemplateSerializer, ClauseSerializer
)
from authentication.r2_service import R2StorageService


class AdminContractViewSet(viewsets.ModelViewSet):
    """
    Admin ViewSet for comprehensive contract management
    Provides CRUD operations for admin dashboard
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ContractDetailWithWorkflowSerializer
        return ContractSerializer
    
    def get_queryset(self):
        """Get contracts for the authenticated user's tenant"""
        if not self.request.user.tenant_id:
            return Contract.objects.none()
        
        queryset = Contract.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).prefetch_related('approvals', 'edit_history', 'workflow_logs')
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by approval status
        approval_filter = self.request.query_params.get('approval_status')
        if approval_filter == 'pending':
            queryset = queryset.filter(
                approvals__status='pending',
                approvals__approver=self.request.user.user_id
            ).distinct()
        
        return queryset
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create new contract with optional file upload and approval workflow"""
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract data
        file = request.FILES.get('file')
        title = request.data.get('title')
        contract_type = request.data.get('contract_type', '')
        counterparty = request.data.get('counterparty', '')
        value = request.data.get('value')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        approval_required = request.data.get('approval_required', 'true').lower() == 'true'
        approver_ids = request.data.get('approvers', '')  # Comma-separated UUIDs
        
        if not title:
            return Response(
                {'error': 'Title is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Upload file to R2 if provided
            document_r2_key = None
            if file:
                r2_service = R2StorageService()
                document_r2_key = r2_service.upload_file(
                    file, 
                    request.user.tenant_id, 
                    file.name
                )
            
            # Parse approvers
            approver_list = []
            if approver_ids:
                approver_list = [aid.strip() for aid in approver_ids.split(',') if aid.strip()]
            
            # Create contract
            contract = Contract.objects.create(
                tenant_id=request.user.tenant_id,
                title=title,
                contract_type=contract_type,
                counterparty=counterparty,
                value=value,
                start_date=start_date,
                end_date=end_date,
                document_r2_key=document_r2_key,
                created_by=request.user.user_id,
                last_edited_by=request.user.user_id,
                last_edited_at=timezone.now(),
                approval_required=approval_required,
                current_approvers=approver_list,
                status='draft'
            )
            
            # Create approval records if required
            if approval_required and approver_list:
                for idx, approver_id in enumerate(approver_list):
                    ContractApproval.objects.create(
                        contract=contract,
                        version_number=contract.current_version,
                        approver=approver_id,
                        sequence=idx + 1,
                        status='pending'
                    )
                contract.status = 'pending'
                contract.save()
            
            # Log creation
            WorkflowLog.objects.create(
                contract=contract,
                action='created',
                performed_by=request.user.user_id,
                comment=f'Contract created via admin dashboard'
            )
            
            serializer = ContractDetailWithWorkflowSerializer(contract)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to create contract: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """Update contract and track changes in edit history"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Capture old values for edit history
        old_data = {
            'title': instance.title,
            'contract_type': instance.contract_type,
            'status': instance.status,
            'value': str(instance.value) if instance.value else None,
            'counterparty': instance.counterparty,
        }
        
        # Handle file upload
        file = request.FILES.get('file')
        if file:
            r2_service = R2StorageService()
            document_r2_key = r2_service.upload_file(
                file, 
                request.user.tenant_id, 
                file.name
            )
            request.data._mutable = True
            request.data['document_r2_key'] = document_r2_key
        
        # Update contract
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Track changes
        instance.refresh_from_db()
        new_data = {
            'title': instance.title,
            'contract_type': instance.contract_type,
            'status': instance.status,
            'value': str(instance.value) if instance.value else None,
            'counterparty': instance.counterparty,
        }
        
        changes = []
        for field, old_value in old_data.items():
            new_value = new_data.get(field)
            if old_value != new_value:
                changes.append({
                    'field': field,
                    'old_value': old_value,
                    'new_value': new_value
                })
        
        if changes:
            # Update last edited info
            instance.last_edited_by = request.user.user_id
            instance.last_edited_at = timezone.now()
            instance.save()
            
            # Create edit history record
            ContractEditHistory.objects.create(
                contract=instance,
                edited_by=request.user.user_id,
                changes=changes,
                change_summary=f"Updated {len(changes)} field(s)",
                version_before=instance.current_version,
                version_after=instance.current_version
            )
            
            # Log the update
            WorkflowLog.objects.create(
                contract=instance,
                action='clause_updated',
                performed_by=request.user.user_id,
                comment='Contract updated via admin dashboard',
                metadata={'changes': changes}
            )
        
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit contract for approval workflow"""
        contract = self.get_object()
        
        if contract.status != 'draft':
            return Response(
                {'error': 'Only draft contracts can be submitted for approval'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        approver_ids = request.data.get('approvers', [])
        if not approver_ids:
            return Response(
                {'error': 'At least one approver is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Create approval records
            for idx, approver_id in enumerate(approver_ids):
                ContractApproval.objects.create(
                    contract=contract,
                    version_number=contract.current_version,
                    approver=approver_id,
                    sequence=idx + 1,
                    status='pending'
                )
            
            # Update contract status
            contract.status = 'pending'
            contract.approval_required = True
            contract.current_approvers = approver_ids
            contract.save()
            
            # Log submission
            WorkflowLog.objects.create(
                contract=contract,
                action='submitted',
                performed_by=request.user.user_id,
                comment='Contract submitted for approval'
            )
        
        serializer = ContractDetailWithWorkflowSerializer(contract)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_approvals(self, request):
        """Get all contracts pending approval for current user"""
        if not request.user.user_id:
            return Response(
                {'error': 'User ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        pending = ContractApproval.objects.filter(
            approver=request.user.user_id,
            status='pending'
        ).select_related('contract')
        
        contracts = [approval.contract for approval in pending]
        serializer = ContractDetailWithWorkflowSerializer(contracts, many=True)
        
        return Response({
            'count': len(contracts),
            'results': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get dashboard statistics for admin view"""
        if not request.user.tenant_id:
            return Response(
                {'error': 'Tenant ID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        contracts = Contract.objects.filter(tenant_id=request.user.tenant_id)
        
        stats = {
            'total_contracts': contracts.count(),
            'by_status': {
                'draft': contracts.filter(status='draft').count(),
                'pending': contracts.filter(status='pending').count(),
                'approved': contracts.filter(status='approved').count(),
                'rejected': contracts.filter(status='rejected').count(),
                'executed': contracts.filter(status='executed').count(),
            },
            'pending_my_approval': ContractApproval.objects.filter(
                approver=request.user.user_id,
                status='pending'
            ).count(),
            'recently_created': contracts.order_by('-created_at')[:5].values(
                'id', 'title', 'status', 'created_at'
            ),
        }
        
        return Response(stats)


class ApprovalActionView(APIView):
    """
    Handle approval/rejection actions on contracts
    """
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, contract_id):
        """Approve or reject a contract"""
        contract = get_object_or_404(Contract, id=contract_id)
        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        comments = serializer.validated_data.get('comments', '')
        
        # Find pending approval for this user
        try:
            approval = ContractApproval.objects.get(
                contract=contract,
                approver=request.user.user_id,
                status='pending'
            )
        except ContractApproval.DoesNotExist:
            return Response(
                {'error': 'No pending approval found for this user'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Update approval record
        approval.status = 'approved' if action_type == 'approve' else 'rejected'
        approval.responded_at = timezone.now()
        approval.comments = comments
        approval.save()
        
        # Check if all approvals are complete
        all_approvals = contract.approvals.filter(
            version_number=contract.current_version
        )
        
        if action_type == 'reject':
            # If rejected, mark contract as rejected
            contract.status = 'rejected'
            contract.save()
            
            # Cancel other pending approvals
            all_approvals.filter(status='pending').update(
                status='cancelled',
                responded_at=timezone.now()
            )
            
            WorkflowLog.objects.create(
                contract=contract,
                action='rejected',
                performed_by=request.user.user_id,
                comment=comments or 'Contract rejected'
            )
        else:
            # Check if all required approvals are approved
            pending_count = all_approvals.filter(
                status='pending',
                is_required=True
            ).count()
            
            if pending_count == 0:
                # All approvals complete - mark as approved
                contract.status = 'approved'
                contract.is_approved = True
                contract.approved_by = request.user.user_id
                contract.approved_at = timezone.now()
                contract.save()
                
                WorkflowLog.objects.create(
                    contract=contract,
                    action='approved',
                    performed_by=request.user.user_id,
                    comment='All approvals completed'
                )
            else:
                WorkflowLog.objects.create(
                    contract=contract,
                    action='approved',
                    performed_by=request.user.user_id,
                    comment=f'Approved by user (pending {pending_count} more approval(s))'
                )
        
        return Response({
            'message': f'Contract {action_type}d successfully',
            'contract_status': contract.status,
            'approval_status': approval.status
        })


class ContractHistoryView(APIView):
    """
    Get complete edit and approval history for a contract
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, contract_id):
        """Get contract history including edits and workflow logs"""
        contract = get_object_or_404(Contract, id=contract_id)
        
        # Verify user has access (same tenant)
        if contract.tenant_id != request.user.tenant_id:
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        edit_history = contract.edit_history.all()
        workflow_logs = contract.workflow_logs.all()
        approvals = contract.approvals.all()
        
        return Response({
            'contract_id': str(contract.id),
            'title': contract.title,
            'current_status': contract.status,
            'edit_history': ContractEditHistorySerializer(edit_history, many=True).data,
            'workflow_logs': WorkflowLogSerializer(workflow_logs, many=True).data,
            'approvals': ContractApprovalSerializer(approvals, many=True).data,
        })


class AdminTemplateViewSet(viewsets.ModelViewSet):
    """Admin endpoints for managing contract templates"""
    permission_classes = [IsAuthenticated]
    serializer_class = ContractTemplateSerializer
    
    def get_queryset(self):
        if not self.request.user.tenant_id:
            return ContractTemplate.objects.none()
        return ContractTemplate.objects.filter(tenant_id=self.request.user.tenant_id)


class AdminClauseViewSet(viewsets.ModelViewSet):
    """Admin endpoints for managing clauses"""
    permission_classes = [IsAuthenticated]
    serializer_class = ClauseSerializer
    
    def get_queryset(self):
        if not self.request.user.tenant_id:
            return Clause.objects.none()
        return Clause.objects.filter(tenant_id=self.request.user.tenant_id)

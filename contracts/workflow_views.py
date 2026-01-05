"""
Workflow API views - Production-ready RESTful endpoints
Implements all workflow, approval, SLA, audit, and admin endpoints
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .workflow_models import (
    WorkflowDefinition, WorkflowInstance, WorkflowStageApproval,
    SLARule, SLABreach, NotificationQueue, AuditLog, UserRole
)
from .workflow_serializers import (
    WorkflowDefinitionSerializer, WorkflowInstanceSerializer,
    WorkflowStageApprovalSerializer, SLARuleSerializer, SLABreachSerializer,
    NotificationSerializer, AuditLogSerializer, UserRoleSerializer,
    ContractApproveSerializer, WorkflowStartSerializer
)
from .workflow_services import WorkflowEngine, SLAMonitor, NotificationService, AuditLogService
from .models import Contract


class WorkflowDefinitionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for workflow configuration management (Admin only)
    
    GET /api/workflows/config/ - List all workflow definitions
    POST /api/workflows/config/ - Create new workflow
    GET /api/workflows/config/<id>/ - Get workflow details
    PUT/PATCH /api/workflows/config/<id>/ - Update workflow
    DELETE /api/workflows/config/<id>/ - Delete workflow
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowDefinitionSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        return WorkflowDefinition.objects.filter(tenant_id=tenant_id)
    
    def perform_create(self, serializer):
        serializer.save(
            tenant_id=self.request.user.tenant_id,
            created_by=self.request.user.user_id
        )
        
        AuditLogService.log(
            tenant_id=self.request.user.tenant_id,
            user_id=self.request.user.user_id,
            action='settings_changed',
            resource_type='workflow_definition',
            resource_id=serializer.instance.id,
            metadata={'workflow_name': serializer.instance.name}
        )


class WorkflowInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing workflow instances
    
    GET /api/workflows/instances/ - List all workflow instances
    GET /api/workflows/instances/<id>/ - Get instance details
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WorkflowInstanceSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        return WorkflowInstance.objects.filter(
            contract__tenant_id=tenant_id
        ).select_related('contract', 'workflow_definition')


class ApprovalViewSet(viewsets.ViewSet):
    """
    API endpoint for approval management
    
    GET /api/approvals/ - List contracts awaiting my approval
    GET /api/approvals/pending/ - List contracts awaiting my approval (alias)
    POST /api/contracts/<id>/approve/ - Approve/reject/delegate contract
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """List pending approvals (alternative endpoint)"""
        return self.list(request)
    
    def list(self, request):
        """List all pending approvals for current user"""
        user_id = request.user.user_id
        
        pending_approvals = WorkflowStageApproval.objects.filter(
            approver=user_id,
            status='pending'
        ).select_related(
            'workflow_instance__contract',
            'workflow_instance__workflow_definition'
        ).order_by('due_at')
        
        # Build response with contract details
        results = []
        for approval in pending_approvals:
            contract = approval.workflow_instance.contract
            results.append({
                'approval_id': str(approval.id),
                'contract_id': str(contract.id),
                'contract_title': contract.title,
                'contract_type': contract.contract_type,
                'contract_value': str(contract.value) if contract.value else None,
                'stage_name': approval.stage_name,
                'stage_sequence': approval.stage_sequence,
                'requested_at': approval.requested_at,
                'due_at': approval.due_at,
                'is_overdue': approval.is_overdue(),
                'workflow_name': approval.workflow_instance.workflow_definition.name,
                'counterparty': contract.counterparty,
            })
        
        return Response({
            'count': len(results),
            'results': results
        })


class SLARuleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for SLA rule management (Admin)
    
    POST /api/admin/sla-rules/ - Create SLA rule
    GET /api/admin/sla-rules/ - List SLA rules
    PUT/PATCH /api/admin/sla-rules/<id>/ - Update SLA rule
    DELETE /api/admin/sla-rules/<id>/ - Delete SLA rule
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SLARuleSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        return SLARule.objects.filter(tenant_id=tenant_id)
    
    def perform_create(self, serializer):
        # Generate name if not provided
        name = serializer.validated_data.get('name')
        if not name:
            workflow = serializer.validated_data.get('workflow_definition')
            stage = serializer.validated_data.get('stage_name', 'General')
            hours = serializer.validated_data.get('sla_hours', 0)
            workflow_name = workflow.name if workflow else 'General'
            name = f"{workflow_name} - {stage} ({hours}h)"
        
        serializer.save(
            tenant_id=self.request.user.tenant_id,
            created_by=self.request.user.user_id,
            name=name
        )
        
        AuditLogService.log(
            tenant_id=self.request.user.tenant_id,
            user_id=self.request.user.user_id,
            action='sla_rule_created',
            resource_type='sla_rule',
            resource_id=serializer.instance.id,
            metadata={'sla_name': serializer.instance.name, 'sla_hours': serializer.instance.sla_hours}
        )


class SLABreachViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for SLA breach tracking (Admin)
    
    GET /api/admin/sla-breaches/ - List all SLA breaches
    GET /api/admin/sla-breaches/<id>/ - Get breach details
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SLABreachSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        queryset = SLABreach.objects.filter(
            workflow_instance__contract__tenant_id=tenant_id
        ).select_related(
            'workflow_instance__contract',
            'stage_approval',
            'sla_rule'
        )
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-breach_time')
    
    @action(detail=False, methods=['post'])
    def check_breaches(self, request):
        """Manually trigger SLA breach check"""
        breaches = SLAMonitor.check_sla_breaches()
        
        return Response({
            'message': f'SLA breach check completed',
            'breaches_found': len(breaches),
            'breach_ids': [str(b.id) for b in breaches]
        }, status=status.HTTP_200_OK)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for audit logs (Admin)
    
    GET /api/audit-logs/ - Global audit log view
    GET /api/contracts/<id>/audit/ - Contract-specific audit log
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AuditLogSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        queryset = AuditLog.objects.filter(tenant_id=tenant_id)
        
        # Filter by contract if provided
        contract_id = self.request.query_params.get('contract_id', None)
        if contract_id:
            queryset = queryset.filter(contract_id=contract_id)
        
        # Filter by action type if provided
        action = self.request.query_params.get('action', None)
        if action:
            queryset = queryset.filter(action=action)
        
        # Filter by user if provided
        user_id = self.request.query_params.get('user_id', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        return queryset.order_by('-timestamp')


class UserRoleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for user role management (Admin)
    
    POST /api/admin/users/roles/ - Assign role to user
    GET /api/admin/users/roles/ - List all role assignments
    DELETE /api/admin/users/roles/<id>/ - Remove role assignment
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserRoleSerializer
    
    def get_queryset(self):
        tenant_id = self.request.user.tenant_id
        queryset = UserRole.objects.filter(tenant_id=tenant_id)
        
        # Filter by user if provided
        user_id = self.request.query_params.get('user_id', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by role if provided
        role = self.request.query_params.get('role', None)
        if role:
            queryset = queryset.filter(role=role)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(
            tenant_id=self.request.user.tenant_id,
            assigned_by=self.request.user.user_id
        )
        
        AuditLogService.log(
            tenant_id=self.request.user.tenant_id,
            user_id=self.request.user.user_id,
            action='role_assigned',
            resource_type='user_role',
            resource_id=serializer.instance.id,
            metadata={
                'target_user_id': str(serializer.instance.user_id),
                'role': serializer.instance.role
            }
        )


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for user notifications
    
    GET /api/notifications/ - List my notifications
    POST /api/notifications/<id>/mark-read/ - Mark notification as read
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    
    def get_queryset(self):
        user_id = self.request.user.user_id
        queryset = NotificationQueue.objects.filter(recipient=user_id)
        
        # Filter by read/unread status
        unread_only = self.request.query_params.get('unread', None)
        if unread_only == 'true':
            queryset = queryset.filter(read_at__isnull=True)
        
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        
        if str(notification.recipient) != str(request.user.user_id):
            return Response(
                {'error': 'Not authorized to modify this notification'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])
        
        return Response({
            'message': 'Notification marked as read',
            'read_at': notification.read_at
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        user_id = request.user.user_id
        now = timezone.now()
        
        updated = NotificationQueue.objects.filter(
            recipient=user_id,
            read_at__isnull=True
        ).update(read_at=now)
        
        return Response({
            'message': f'{updated} notifications marked as read'
        }, status=status.HTTP_200_OK)

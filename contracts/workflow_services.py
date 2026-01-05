"""
Workflow engine service - production-ready business logic
Handles workflow execution, approval routing, SLA tracking, and notifications
"""
from django.db import transaction
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
import logging

from .workflow_models import (
    WorkflowDefinition, WorkflowInstance, WorkflowStageApproval,
    SLARule, SLABreach, NotificationQueue, AuditLog, UserRole
)
from .models import Contract

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Core workflow engine for contract approvals
    """
    
    @staticmethod
    def match_workflow(contract):
        """
        Find the most appropriate workflow for a contract based on trigger conditions
        
        Args:
            contract: Contract instance
        
        Returns:
            WorkflowDefinition instance or None
        """
        workflows = WorkflowDefinition.objects.filter(
            tenant_id=contract.tenant_id,
            is_active=True
        ).order_by('-priority')
        
        for workflow in workflows:
            if WorkflowEngine._evaluate_conditions(contract, workflow.trigger_conditions):
                return workflow
        
        return None
    
    @staticmethod
    def _evaluate_conditions(contract, conditions):
        """
        Evaluate trigger conditions against contract attributes
        
        Args:
            contract: Contract instance
            conditions: Dict of conditions to evaluate
        
        Returns:
            bool: True if all conditions match
        """
        if not conditions:
            return True  # No conditions means it applies to all
        
        for field, value in conditions.items():
            # Support Django ORM-style lookups (e.g., contract_value__gte)
            if '__' in field:
                field_name, lookup = field.rsplit('__', 1)
                contract_value = getattr(contract, field_name, None)
                
                if lookup == 'gte' and not (contract_value and contract_value >= value):
                    return False
                elif lookup == 'lte' and not (contract_value and contract_value <= value):
                    return False
                elif lookup == 'gt' and not (contract_value and contract_value > value):
                    return False
                elif lookup == 'lt' and not (contract_value and contract_value < value):
                    return False
                elif lookup == 'in' and contract_value not in value:
                    return False
            else:
                contract_value = getattr(contract, field, None)
                if contract_value != value:
                    return False
        
        return True
    
    @staticmethod
    @transaction.atomic
    def start_workflow(contract, workflow_definition=None, user_id=None, metadata=None):
        """
        Start a workflow for a contract
        
        Args:
            contract: Contract instance
            workflow_definition: WorkflowDefinition (optional, will auto-match if None)
            user_id: User starting the workflow
            metadata: Additional metadata dict
        
        Returns:
            WorkflowInstance
        """
        # Auto-match workflow if not provided
        if not workflow_definition:
            workflow_definition = WorkflowEngine.match_workflow(contract)
            if not workflow_definition:
                raise ValidationError("No matching workflow found for this contract")
        
        # Create workflow instance
        first_stage = workflow_definition.stages[0] if workflow_definition.stages else {}
        instance = WorkflowInstance.objects.create(
            contract=contract,
            workflow_definition=workflow_definition,
            current_stage=first_stage.get('sequence', 0),
            current_stage_name=first_stage.get('stage_name', 'Initial'),
            status='active',
            metadata=metadata or {}
        )
        
        # Create stage approvals for first stage
        WorkflowEngine._create_stage_approvals(instance, first_stage)
        
        # Update contract status
        contract.status = 'pending'
        contract.save(update_fields=['status', 'updated_at'])
        
        # Log audit event
        AuditLogService.log(
            tenant_id=contract.tenant_id,
            user_id=user_id or contract.created_by,
            action='workflow_started',
            resource_type='contract',
            resource_id=contract.id,
            contract=contract,
            metadata={'workflow_id': str(workflow_definition.id), 'workflow_name': workflow_definition.name}
        )
        
        # Send notifications to approvers
        NotificationService.notify_approvers(instance)
        
        logger.info(f"Workflow started for contract {contract.id}: {workflow_definition.name}")
        
        return instance
    
    @staticmethod
    def _create_stage_approvals(workflow_instance, stage_config):
        """
        Create approval records for a workflow stage
        
        Args:
            workflow_instance: WorkflowInstance
            stage_config: Dict with stage configuration
        """
        approvers = stage_config.get('approvers', [])
        sla_hours = stage_config.get('sla_hours', 48)
        is_parallel = stage_config.get('parallel', False)
        
        # Calculate SLA deadline
        due_at = timezone.now() + timedelta(hours=sla_hours)
        
        for approver_spec in approvers:
            approver_ids = WorkflowEngine._resolve_approver(approver_spec, workflow_instance.contract.tenant_id)
            
            for approver_id in approver_ids:
                WorkflowStageApproval.objects.create(
                    workflow_instance=workflow_instance,
                    stage_sequence=stage_config.get('sequence', 0),
                    stage_name=stage_config.get('stage_name', 'Approval'),
                    approver=approver_id,
                    approver_role=approver_spec if approver_spec.startswith('role:') else None,
                    is_required=stage_config.get('required', True),
                    due_at=due_at
                )
    
    @staticmethod
    def _resolve_approver(approver_spec, tenant_id):
        """
        Resolve approver specification to user IDs
        
        Args:
            approver_spec: String like "user:uuid" or "role:legal"
            tenant_id: Tenant ID
        
        Returns:
            List of user IDs
        """
        if approver_spec.startswith('user:'):
            return [approver_spec.split(':', 1)[1]]
        elif approver_spec.startswith('role:'):
            role = approver_spec.split(':', 1)[1]
            user_roles = UserRole.objects.filter(
                tenant_id=tenant_id,
                role=role,
                is_active=True
            ).values_list('user_id', flat=True)
            return list(user_roles)
        else:
            return [approver_spec]  # Assume it's a direct user ID
    
    @staticmethod
    @transaction.atomic
    def process_approval(approval, action, user_id, comments=None, delegate_to=None):
        """
        Process an approval action (approve/reject/delegate)
        
        Args:
            approval: WorkflowStageApproval instance
            action: 'approve', 'reject', or 'delegate'
            user_id: User taking the action
            comments: Optional comments
            delegate_to: User ID if delegating
        
        Returns:
            Updated WorkflowInstance
        """
        if approval.status != 'pending':
            raise ValidationError(f"Approval is already {approval.status}")
        
        if str(approval.approver) != str(user_id) and not delegate_to:
            raise ValidationError("You are not authorized to perform this approval")
        
        # Update approval record
        approval.responded_at = timezone.now()
        approval.comments = comments
        
        if action == 'approve':
            approval.status = 'approved'
            audit_action = 'approval_approved'
        elif action == 'reject':
            approval.status = 'rejected'
            audit_action = 'approval_rejected'
        elif action == 'delegate':
            approval.status = 'delegated'
            approval.delegated_to = delegate_to
            approval.delegation_reason = comments
            audit_action = 'approval_delegated'
            
            # Create new approval for delegated user
            new_approval = WorkflowStageApproval.objects.create(
                workflow_instance=approval.workflow_instance,
                stage_sequence=approval.stage_sequence,
                stage_name=approval.stage_name,
                approver=delegate_to,
                is_required=approval.is_required,
                due_at=approval.due_at
            )
            
            NotificationService.notify_single_approver(new_approval, "Approval Delegated to You")
        
        approval.save()
        
        # Log audit event
        AuditLogService.log(
            tenant_id=approval.workflow_instance.contract.tenant_id,
            user_id=user_id,
            action=audit_action,
            resource_type='workflow_approval',
            resource_id=approval.id,
            contract=approval.workflow_instance.contract,
            metadata={'stage': approval.stage_name, 'comments': comments}
        )
        
        # Check if we can advance the workflow
        if action in ['approve', 'reject']:
            return WorkflowEngine._check_stage_completion(approval.workflow_instance)
        
        return approval.workflow_instance
    
    @staticmethod
    def _check_stage_completion(workflow_instance):
        """
        Check if current stage is complete and advance if needed
        
        Args:
            workflow_instance: WorkflowInstance
        
        Returns:
            Updated WorkflowInstance
        """
        current_approvals = WorkflowStageApproval.objects.filter(
            workflow_instance=workflow_instance,
            stage_sequence=workflow_instance.current_stage
        )
        
        # Check for any rejections
        if current_approvals.filter(status='rejected').exists():
            workflow_instance.contract.status = 'rejected'
            workflow_instance.contract.save(update_fields=['status', 'updated_at'])
            workflow_instance.status = 'completed'
            workflow_instance.completed_at = timezone.now()
            workflow_instance.save(update_fields=['status', 'completed_at'])
            return workflow_instance
        
        # Check if all required approvals are complete
        required_approvals = current_approvals.filter(is_required=True)
        pending_required = required_approvals.filter(status='pending').count()
        
        if pending_required == 0:
            # All required approvals done, advance to next stage
            next_stage = WorkflowEngine._get_next_stage(workflow_instance)
            
            if next_stage:
                workflow_instance.current_stage = next_stage['sequence']
                workflow_instance.current_stage_name = next_stage['stage_name']
                workflow_instance.save(update_fields=['current_stage', 'current_stage_name'])
                
                # Create approvals for next stage
                WorkflowEngine._create_stage_approvals(workflow_instance, next_stage)
                NotificationService.notify_approvers(workflow_instance)
            else:
                # Workflow complete
                workflow_instance.status = 'completed'
                workflow_instance.completed_at = timezone.now()
                workflow_instance.contract.status = 'approved'
                workflow_instance.contract.is_approved = True
                workflow_instance.contract.approved_at = timezone.now()
                workflow_instance.contract.save(update_fields=['status', 'is_approved', 'approved_at', 'updated_at'])
                workflow_instance.save(update_fields=['status', 'completed_at'])
                
                NotificationService.notify_workflow_complete(workflow_instance)
        
        return workflow_instance
    
    @staticmethod
    def _get_next_stage(workflow_instance):
        """
        Get the next stage in the workflow
        
        Args:
            workflow_instance: WorkflowInstance
        
        Returns:
            Dict of next stage config or None
        """
        stages = workflow_instance.workflow_definition.stages
        current_seq = workflow_instance.current_stage
        
        next_stages = [s for s in stages if s.get('sequence', 0) > current_seq]
        if next_stages:
            return min(next_stages, key=lambda s: s.get('sequence', 0))
        
        return None


class SLAMonitor:
    """
    Service for monitoring and enforcing SLA rules
    """
    
    @staticmethod
    def check_sla_breaches():
        """
        Check for SLA breaches and create breach records
        
        Returns:
            List of created SLABreach instances
        """
        breaches = []
        now = timezone.now()
        
        # Find overdue approvals
        overdue_approvals = WorkflowStageApproval.objects.filter(
            status='pending',
            due_at__lt=now
        ).select_related('workflow_instance', 'workflow_instance__contract')
        
        for approval in overdue_approvals:
            # Check if breach already recorded
            existing_breach = SLABreach.objects.filter(
                stage_approval=approval,
                status='active'
            ).exists()
            
            if not existing_breach:
                # Calculate breach duration
                breach_duration = (now - approval.due_at).total_seconds() / 3600  # hours
                
                # Find applicable SLA rule
                sla_rule = SLAMonitor._find_sla_rule(approval)
                
                breach = SLABreach.objects.create(
                    workflow_instance=approval.workflow_instance,
                    stage_approval=approval,
                    sla_rule=sla_rule,
                    expected_completion=approval.due_at,
                    breach_duration_hours=breach_duration
                )
                
                breaches.append(breach)
                
                # Send escalation if enabled
                if sla_rule and sla_rule.escalation_enabled:
                    SLAMonitor._escalate_breach(breach, sla_rule)
                
                logger.warning(f"SLA breach detected: {approval.workflow_instance.contract.title} - {breach_duration:.1f}h overdue")
        
        return breaches
    
    @staticmethod
    def _find_sla_rule(approval):
        """Find applicable SLA rule for an approval"""
        return SLARule.objects.filter(
            tenant_id=approval.workflow_instance.contract.tenant_id,
            is_active=True,
            workflow_definition=approval.workflow_instance.workflow_definition
        ).filter(
            models.Q(stage_name=approval.stage_name) | models.Q(stage_name__isnull=True)
        ).first()
    
    @staticmethod
    def _escalate_breach(breach, sla_rule):
        """Send escalation notifications for SLA breach"""
        for user_id in sla_rule.escalation_users:
            message = sla_rule.escalation_message or (
                f"SLA BREACH: Contract '{breach.workflow_instance.contract.title}' "
                f"has exceeded the {sla_rule.sla_hours}h SLA for stage '{breach.stage_approval.stage_name}'. "
                f"Currently {breach.breach_duration_hours:.1f}h overdue."
            )
            
            NotificationQueue.objects.create(
                recipient=user_id,
                notification_type='both',
                subject=f"SLA Breach: {breach.workflow_instance.contract.title}",
                message=message,
                contract=breach.workflow_instance.contract,
                workflow_instance=breach.workflow_instance,
                priority=10,  # High priority
                metadata={'breach_id': str(breach.id), 'sla_rule_id': str(sla_rule.id)}
            )
        
        breach.escalated = True
        breach.escalation_sent_at = timezone.now()
        breach.save(update_fields=['escalated', 'escalation_sent_at'])


class NotificationService:
    """
    Service for sending notifications to users
    """
    
    @staticmethod
    def notify_approvers(workflow_instance):
        """Send notifications to all current stage approvers"""
        current_approvals = WorkflowStageApproval.objects.filter(
            workflow_instance=workflow_instance,
            stage_sequence=workflow_instance.current_stage,
            status='pending'
        )
        
        for approval in current_approvals:
            NotificationService.notify_single_approver(approval, "Approval Required")
    
    @staticmethod
    def notify_single_approver(approval, subject_prefix="Approval Required"):
        """Send notification to a single approver"""
        message = (
            f"You have been requested to approve contract '{approval.workflow_instance.contract.title}' "
            f"for stage '{approval.stage_name}'. "
            f"Please review and provide your approval by {approval.due_at.strftime('%Y-%m-%d %H:%M')}."
        )
        
        NotificationQueue.objects.create(
            recipient=approval.approver,
            notification_type='both',
            subject=f"{subject_prefix}: {approval.workflow_instance.contract.title}",
            message=message,
            contract=approval.workflow_instance.contract,
            workflow_instance=approval.workflow_instance,
            priority=5,
            metadata={
                'approval_id': str(approval.id),
                'stage': approval.stage_name,
                'due_at': approval.due_at.isoformat()
            }
        )
    
    @staticmethod
    def notify_workflow_complete(workflow_instance):
        """Notify relevant users when workflow completes"""
        message = (
            f"Workflow for contract '{workflow_instance.contract.title}' has been completed. "
            f"The contract has been approved and is ready for execution."
        )
        
        # Notify contract creator
        NotificationQueue.objects.create(
            recipient=workflow_instance.contract.created_by,
            notification_type='both',
            subject=f"Contract Approved: {workflow_instance.contract.title}",
            message=message,
            contract=workflow_instance.contract,
            workflow_instance=workflow_instance,
            priority=5,
            metadata={'workflow_status': 'completed'}
        )


class AuditLogService:
    """
    Service for creating audit log entries
    """
    
    @staticmethod
    def log(tenant_id, user_id, action, resource_type, resource_id, contract=None, 
            ip_address=None, user_agent=None, changes=None, metadata=None):
        """
        Create an audit log entry
        
        Args:
            tenant_id: Tenant ID
            user_id: User performing action
            action: Action performed (from AuditLog.ACTION_CHOICES)
            resource_type: Type of resource
            resource_id: Resource ID
            contract: Related contract (optional)
            ip_address: User IP address (optional)
            user_agent: User agent string (optional)
            changes: Dict of changes (optional)
            metadata: Additional metadata (optional)
        
        Returns:
            AuditLog instance
        """
        return AuditLog.objects.create(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            contract=contract,
            ip_address=ip_address,
            user_agent=user_agent,
            changes=changes or {},
            metadata=metadata or {}
        )

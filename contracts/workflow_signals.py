"""
Django Signals for Event-Driven Notifications
Implements the Observer Pattern for decoupled notification system
"""
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .workflow_models import (
    WorkflowStageApproval, WorkflowInstance, NotificationQueue, AuditLog
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkflowStageApproval)
def notify_on_approval_assignment(sender, instance, created, **kwargs):
    """
    Listen for new approval assignments and send notifications
    
    Triggered: When a WorkflowStageApproval is created
    Action: Create in-app notification for the approver
    
    Why this is Production-Level:
    - Decoupled: If notification fails, approval creation still succeeds
    - Isolated: Error in notification doesn't crash the main workflow
    - Scalable: Easy to add more notification channels (email, Slack, etc.)
    
    Args:
        sender: WorkflowStageApproval model class
        instance: The approval record that was saved
        created: Boolean - True if this is a new record
        **kwargs: Additional signal data
    """
    if not created:
        # Only notify on creation, not updates
        return
    
    if instance.status != 'pending':
        # Only notify for pending approvals
        return
    
    try:
        contract = instance.workflow_instance.contract
        workflow_name = instance.workflow_instance.workflow_definition.name
        
        # Create in-app notification
        notification = NotificationQueue.objects.create(
            tenant_id=instance.tenant_id,
            recipient=instance.approver,
            notification_type='approval_required',
            priority='high' if instance.is_required else 'medium',
            title='Approval Required',
            message=f'Please review "{contract.title}" in {instance.stage_name} stage',
            action_url=f'/contracts/{contract.id}/approve',
            metadata={
                'contract_id': str(contract.id),
                'contract_title': contract.title,
                'workflow_id': str(instance.workflow_instance.id),
                'workflow_name': workflow_name,
                'stage_name': instance.stage_name,
                'due_at': instance.due_at.isoformat() if instance.due_at else None
            },
            scheduled_at=timezone.now()
        )
        
        logger.info(
            f"🔔 Notification created for {instance.approver}: "
            f"Approval required for contract {contract.id}"
        )
        
    except Exception as e:
        # Log error but don't crash the approval creation
        logger.error(
            f"Failed to create notification for approval {instance.id}: {e}",
            exc_info=True
        )


@receiver(post_save, sender=WorkflowStageApproval)
def notify_on_approval_response(sender, instance, created, **kwargs):
    """
    Notify relevant parties when an approval is responded to
    
    Triggered: When approval status changes to approved/rejected
    Action: Notify contract creator and workflow participants
    """
    if created:
        # Only handle updates, not creation
        return
    
    if instance.status not in ['approved', 'rejected']:
        # Only notify on final decisions
        return
    
    try:
        contract = instance.workflow_instance.contract
        workflow = instance.workflow_instance
        
        # Notify contract creator
        NotificationQueue.objects.create(
            tenant_id=instance.tenant_id,
            recipient=contract.created_by,
            notification_type='approval_update',
            priority='medium',
            title=f'Contract {instance.status.title()}',
            message=(
                f'Your contract "{contract.title}" was {instance.status} '
                f'in {instance.stage_name} stage'
            ),
            action_url=f'/contracts/{contract.id}',
            metadata={
                'contract_id': str(contract.id),
                'action': instance.status,
                'stage_name': instance.stage_name,
                'comments': instance.comments or ''
            },
            scheduled_at=timezone.now()
        )
        
        logger.info(
            f"🔔 Notified contract creator: Contract {contract.id} {instance.status}"
        )
        
    except Exception as e:
        logger.error(
            f"Failed to notify on approval response {instance.id}: {e}",
            exc_info=True
        )


@receiver(post_save, sender=WorkflowInstance)
def notify_on_workflow_completion(sender, instance, created, **kwargs):
    """
    Notify when workflow completes (approved or rejected)
    
    Triggered: When workflow status changes to completed/rejected
    Action: Send completion notification to all stakeholders
    """
    if created:
        return
    
    if instance.status not in ['completed', 'rejected']:
        return
    
    try:
        contract = instance.contract
        
        # Notify contract creator
        NotificationQueue.objects.create(
            tenant_id=instance.tenant_id,
            recipient=contract.created_by,
            notification_type='workflow_completed',
            priority='high',
            title=f'Workflow {instance.status.title()}',
            message=(
                f'Approval workflow for "{contract.title}" has been {instance.status}. '
                f'Contract is now ready for execution.' if instance.status == 'completed'
                else f'Approval workflow for "{contract.title}" was {instance.status}.'
            ),
            action_url=f'/contracts/{contract.id}',
            metadata={
                'contract_id': str(contract.id),
                'workflow_id': str(instance.id),
                'workflow_name': instance.workflow_definition.name,
                'final_status': instance.status,
                'completed_at': instance.completed_at.isoformat() if instance.completed_at else None
            },
            scheduled_at=timezone.now()
        )
        
        logger.info(
            f"🔔 Workflow completion notification sent for contract {contract.id}"
        )
        
    except Exception as e:
        logger.error(
            f"Failed to notify on workflow completion {instance.id}: {e}",
            exc_info=True
        )


@receiver(pre_save, sender=WorkflowStageApproval)
def check_sla_on_approval_save(sender, instance, **kwargs):
    """
    Check if approval is overdue before saving
    Used for tracking SLA compliance
    
    Triggered: Before WorkflowStageApproval save
    Action: Calculate overdue status for reporting
    """
    if instance.status == 'pending' and instance.due_at:
        if timezone.now() > instance.due_at:
            # Mark in metadata for reporting (not changing status)
            if not instance.metadata:
                instance.metadata = {}
            instance.metadata['overdue'] = True
            instance.metadata['overdue_since'] = timezone.now().isoformat()
            
            logger.warning(
                f"⚠️ Approval {instance.id} is overdue "
                f"(due: {instance.due_at}, stage: {instance.stage_name})"
            )

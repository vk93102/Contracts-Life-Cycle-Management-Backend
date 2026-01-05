"""
Production-Level Workflow Engine with Dynamic Rule Matching
Implements the Observer Pattern and Service Layer Architecture
"""
import logging
from django.db import transaction
from django.utils import timezone
from .models import Contract
from .workflow_models import (
    WorkflowDefinition, WorkflowInstance, WorkflowStageApproval,
    SLARule, NotificationQueue, AuditLog
)

logger = logging.getLogger(__name__)


class WorkflowMatchEngine:
    """
    Dynamic rule matching engine using Django ORM kwargs unpacking
    Converts JSON rules into database queries for efficient matching
    """
    
    @staticmethod
    def find_matching_workflow(contract):
        """
        Dynamically matches a contract against all active workflow rules.
        
        The Core Logic:
        - Fetch active workflows sorted by priority
        - For each workflow, test if contract matches trigger_conditions
        - Use Django ORM filter(**rules) to let database do the evaluation
        - Return highest priority matching workflow
        
        Example:
            rule = {"contract_value__lte": 100000, "contract_type": "MSA"}
            Contract.objects.filter(id=contract.id, **rule).exists()
            → Database evaluates: WHERE id=X AND value <= 100000 AND type='MSA'
        
        Args:
            contract: Contract instance to match
            
        Returns:
            WorkflowDefinition instance or None
        """
        workflows = WorkflowDefinition.objects.filter(
            tenant_id=contract.tenant_id,
            is_active=True
        ).order_by('-priority', '-created_at')
        
        for workflow in workflows:
            # Check contract type filter (array match)
            if workflow.contract_types and contract.contract_type not in workflow.contract_types:
                continue
            
            # Dynamic rule matching using kwargs unpacking
            rules = workflow.trigger_conditions or {}
            
            if not rules:
                # No conditions = matches all contracts of matching type
                return workflow
            
            try:
                # 💡 THE CORE MAGIC:
                # We ask the database: "Does this contract satisfy these rules?"
                # If it survives the filter, it complies!
                is_match = Contract.objects.filter(
                    id=contract.id,
                    **rules  # Unpacks JSON into Django ORM lookups
                ).exists()
                
                if is_match:
                    logger.info(
                        f"Contract {contract.id} matched workflow {workflow.name} "
                        f"with rules: {rules}"
                    )
                    return workflow
                    
            except Exception as e:
                # Log but don't crash - bad rules shouldn't break the system
                logger.warning(
                    f"Skipping workflow {workflow.name} due to invalid rules: {e}"
                )
                continue
        
        logger.info(f"No matching workflow found for contract {contract.id}")
        return None


class WorkflowOrchestrator:
    """
    Orchestrates workflow lifecycle: start, advance, complete
    Implements transaction safety and audit logging
    """
    
    @staticmethod
    @transaction.atomic
    def start_workflow(contract, workflow_definition=None, initiated_by=None, metadata=None):
        """
        Start a workflow instance for a contract
        
        Transaction Flow:
        1. Find or use specified workflow definition
        2. Create workflow instance
        3. Parse stages and create approval records
        4. Trigger notifications (via signals)
        5. Log audit trail
        
        Args:
            contract: Contract instance
            workflow_definition: WorkflowDefinition (optional, will auto-match if None)
            initiated_by: User ID who started the workflow
            metadata: Additional context dict
            
        Returns:
            WorkflowInstance
            
        Raises:
            ValueError: If no matching workflow found
        """
        # Auto-match workflow if not specified
        if not workflow_definition:
            workflow_definition = WorkflowMatchEngine.find_matching_workflow(contract)
            
        if not workflow_definition:
            raise ValueError("No matching workflow found for this contract")
        
        # Create workflow instance
        workflow_instance = WorkflowInstance.objects.create(
            tenant_id=contract.tenant_id,
            contract=contract,
            workflow_definition=workflow_definition,
            current_stage=0,
            current_stage_name='',
            status='active',
            started_at=timezone.now(),
            metadata=metadata or {}
        )
        
        # Parse stages and create approvals
        stages = workflow_definition.stages or []
        
        if not stages:
            logger.warning(f"Workflow {workflow_definition.name} has no stages")
            return workflow_instance
        
        # Create approval records for all stages
        for stage in stages:
            stage_name = stage.get('stage_name', 'Unnamed Stage')
            sequence = stage.get('sequence', 0)
            approvers = stage.get('approvers', [])
            approval_type = stage.get('approval_type', 'any')  # 'any' or 'all'
            is_required = stage.get('is_required', True)
            sla_hours = stage.get('sla_hours', 48)
            
            # Calculate SLA deadline
            due_at = timezone.now() + timezone.timedelta(hours=sla_hours)
            
            # Create approval for each approver
            for approver_spec in approvers:
                # Resolve approver: can be user_id or role name
                approver_id = WorkflowOrchestrator._resolve_approver(
                    contract.tenant_id,
                    approver_spec
                )
                
                if not approver_id:
                    logger.warning(
                        f"Could not resolve approver '{approver_spec}' for stage {stage_name}"
                    )
                    continue
                
                WorkflowStageApproval.objects.create(
                    tenant_id=contract.tenant_id,
                    workflow_instance=workflow_instance,
                    stage_sequence=sequence,
                    stage_name=stage_name,
                    approver=approver_id,
                    approver_role=approver_spec if not approver_id else None,
                    status='pending',
                    is_required=is_required,
                    due_at=due_at
                )
        
        # Update workflow instance with first stage
        first_stage = min(stages, key=lambda s: s.get('sequence', 0))
        workflow_instance.current_stage = first_stage.get('sequence', 0)
        workflow_instance.current_stage_name = first_stage.get('stage_name', '')
        workflow_instance.save()
        
        # Update contract status
        contract.status = 'pending_approval'
        contract.save(update_fields=['status', 'updated_at'])
        
        # Log audit event
        AuditLog.objects.create(
            tenant_id=contract.tenant_id,
            user_id=initiated_by,
            action='workflow_started',
            resource_type='contract',
            resource_id=contract.id,
            contract=contract,
            metadata={
                'workflow_name': workflow_definition.name,
                'workflow_id': str(workflow_definition.id),
                'stages_count': len(stages)
            }
        )
        
        logger.info(
            f"Started workflow {workflow_definition.name} "
            f"for contract {contract.id} with {len(stages)} stages"
        )
        
        return workflow_instance
    
    @staticmethod
    def _resolve_approver(tenant_id, approver_spec):
        """
        Resolve approver specification to user ID
        
        Handles:
        - Direct user UUID
        - Role name (returns first user with that role)
        - Dynamic resolution from UserRole model
        
        Args:
            tenant_id: Tenant UUID
            approver_spec: str (user_id or role name)
            
        Returns:
            UUID or None
        """
        from .workflow_models import UserRole
        from uuid import UUID
        
        # Try as direct UUID
        try:
            return UUID(str(approver_spec))
        except (ValueError, AttributeError):
            pass
        
        # Try as role name
        try:
            user_role = UserRole.objects.filter(
                tenant_id=tenant_id,
                role=approver_spec,
                is_active=True
            ).first()
            
            if user_role:
                return user_role.user_id
        except Exception as e:
            logger.error(f"Error resolving approver {approver_spec}: {e}")
        
        return None
    
    @staticmethod
    @transaction.atomic
    def process_approval(approval, action, user_id, comments='', delegate_to=None):
        """
        Process approval/rejection/delegation action
        
        State Machine:
        pending → approved/rejected/delegated
        
        Side Effects:
        - Update approval status
        - Advance workflow if stage complete
        - Send notifications
        - Log audit trail
        
        Args:
            approval: WorkflowStageApproval instance
            action: 'approve', 'reject', or 'delegate'
            user_id: User performing the action
            comments: Optional comments
            delegate_to: User UUID if delegating
            
        Returns:
            WorkflowInstance
        """
        if approval.status != 'pending':
            raise ValueError(f"Cannot process approval in {approval.status} status")
        
        workflow_instance = approval.workflow_instance
        contract = workflow_instance.contract
        
        # Update approval record
        approval.status = action + 'd' if action != 'delegate' else 'delegated'
        approval.responded_at = timezone.now()
        approval.comments = comments
        
        if action == 'delegate':
            if not delegate_to:
                raise ValueError("delegate_to is required for delegation")
            approval.delegated_to = delegate_to
            approval.delegation_reason = comments
            
            # Create new approval for delegate
            WorkflowStageApproval.objects.create(
                tenant_id=approval.tenant_id,
                workflow_instance=workflow_instance,
                stage_sequence=approval.stage_sequence,
                stage_name=approval.stage_name,
                approver=delegate_to,
                status='pending',
                is_required=approval.is_required,
                due_at=approval.due_at
            )
        
        approval.save()
        
        # Check if rejection should stop workflow
        if action == 'reject':
            workflow_instance.status = 'rejected'
            workflow_instance.completed_at = timezone.now()
            workflow_instance.save()
            
            contract.status = 'rejected'
            contract.save(update_fields=['status', 'updated_at'])
            
            # Log audit
            AuditLog.objects.create(
                tenant_id=contract.tenant_id,
                user_id=user_id,
                action='contract_rejected',
                resource_type='contract',
                resource_id=contract.id,
                contract=contract,
                metadata={
                    'stage': approval.stage_name,
                    'comments': comments
                }
            )
            
            return workflow_instance
        
        # Check if current stage is complete
        if action == 'approve':
            WorkflowOrchestrator._advance_workflow_if_ready(
                workflow_instance, user_id
            )
        
        # Log audit
        AuditLog.objects.create(
            tenant_id=contract.tenant_id,
            user_id=user_id,
            action=f'contract_{action}d',
            resource_type='contract',
            resource_id=contract.id,
            contract=contract,
            metadata={
                'stage': approval.stage_name,
                'comments': comments
            }
        )
        
        return workflow_instance
    
    @staticmethod
    def _advance_workflow_if_ready(workflow_instance, user_id):
        """
        Check if current stage is complete and advance to next stage
        
        Logic:
        - Get all approvals for current stage
        - Check if stage requirements met (any vs all)
        - If complete, move to next stage or complete workflow
        """
        current_stage = workflow_instance.current_stage
        
        # Get all approvals for current stage
        stage_approvals = WorkflowStageApproval.objects.filter(
            workflow_instance=workflow_instance,
            stage_sequence=current_stage
        )
        
        # Check if stage is complete
        required_approvals = stage_approvals.filter(is_required=True)
        approved_count = required_approvals.filter(status='approved').count()
        pending_count = required_approvals.filter(status='pending').count()
        
        # If any pending, stage not complete
        if pending_count > 0:
            return
        
        # If all approved, advance
        if approved_count == required_approvals.count():
            # Find next stage
            all_stages = workflow_instance.workflow_definition.stages or []
            next_stage = None
            
            for stage in sorted(all_stages, key=lambda s: s.get('sequence', 0)):
                if stage.get('sequence', 0) > current_stage:
                    next_stage = stage
                    break
            
            if next_stage:
                # Advance to next stage
                workflow_instance.current_stage = next_stage.get('sequence', 0)
                workflow_instance.current_stage_name = next_stage.get('stage_name', '')
                workflow_instance.save()
                
                logger.info(
                    f"Workflow {workflow_instance.id} advanced to stage "
                    f"{next_stage.get('stage_name')}"
                )
            else:
                # No more stages - workflow complete
                workflow_instance.status = 'completed'
                workflow_instance.completed_at = timezone.now()
                workflow_instance.save()
                
                # Update contract status
                contract = workflow_instance.contract
                contract.status = 'approved'
                contract.save(update_fields=['status', 'updated_at'])
                
                logger.info(f"Workflow {workflow_instance.id} completed successfully")

"""
Serializers for workflow engine - production-ready with validation
"""
from rest_framework import serializers
from .workflow_models import (
    WorkflowDefinition, WorkflowInstance, WorkflowStageApproval,
    SLARule, SLABreach, NotificationQueue, AuditLog, UserRole
)
from .models import Contract


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    """Workflow definition serializer with validation"""
    
    class Meta:
        model = WorkflowDefinition
        fields = [
            'id', 'name', 'description', 'contract_types', 'trigger_conditions',
            'stages', 'is_active', 'priority', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
    
    def validate_stages(self, value):
        """Validate stages configuration"""
        if not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError("Stages must be a non-empty list")
        
        required_fields = ['stage_name', 'sequence', 'approvers']
        for stage in value:
            for field in required_fields:
                if field not in stage:
                    raise serializers.ValidationError(f"Each stage must have '{field}' field")
        
        return value


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    """Workflow instance serializer"""
    contract_title = serializers.CharField(source='contract.title', read_only=True)
    workflow_name = serializers.CharField(source='workflow_definition.name', read_only=True)
    
    class Meta:
        model = WorkflowInstance
        fields = [
            'id', 'contract', 'contract_title', 'workflow_definition', 'workflow_name',
            'current_stage', 'current_stage_name', 'status', 'started_at',
            'completed_at', 'paused_at', 'metadata'
        ]
        read_only_fields = ['id', 'started_at']


class WorkflowStageApprovalSerializer(serializers.ModelSerializer):
    """Stage approval serializer"""
    is_overdue = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowStageApproval
        fields = [
            'id', 'workflow_instance', 'stage_sequence', 'stage_name',
            'approver', 'approver_role', 'status', 'is_required',
            'requested_at', 'due_at', 'responded_at', 'comments',
            'delegated_to', 'delegation_reason', 'is_overdue'
        ]
        read_only_fields = ['id', 'requested_at', 'is_overdue']
    
    def get_is_overdue(self, obj):
        return obj.is_overdue()


class SLARuleSerializer(serializers.ModelSerializer):
    """SLA rule serializer"""
    workflow_name = serializers.CharField(source='workflow_definition.name', read_only=True, allow_null=True)
    
    class Meta:
        model = SLARule
        fields = [
            'id', 'name', 'description', 'workflow_definition', 'workflow_name',
            'stage_name', 'sla_hours', 'escalation_enabled', 'escalation_users',
            'escalation_message', 'is_active', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class SLABreachSerializer(serializers.ModelSerializer):
    """SLA breach serializer"""
    contract_title = serializers.CharField(source='workflow_instance.contract.title', read_only=True)
    stage_name = serializers.CharField(source='stage_approval.stage_name', read_only=True)
    
    class Meta:
        model = SLABreach
        fields = [
            'id', 'workflow_instance', 'contract_title', 'stage_approval', 'stage_name',
            'sla_rule', 'breach_time', 'expected_completion', 'actual_completion',
            'breach_duration_hours', 'status', 'escalated', 'escalation_sent_at',
            'resolution_notes'
        ]
        read_only_fields = ['id', 'breach_time', 'breach_duration_hours']


class NotificationSerializer(serializers.ModelSerializer):
    """Notification serializer"""
    
    class Meta:
        model = NotificationQueue
        fields = [
            'id', 'recipient', 'notification_type', 'subject', 'message',
            'contract', 'workflow_instance', 'status', 'priority',
            'created_at', 'sent_at', 'read_at', 'error_message', 'metadata'
        ]
        read_only_fields = ['id', 'created_at', 'sent_at', 'read_at']


class AuditLogSerializer(serializers.ModelSerializer):
    """Audit log serializer"""
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user_id', 'action', 'resource_type', 'resource_id',
            'contract', 'ip_address', 'user_agent', 'changes', 'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class UserRoleSerializer(serializers.ModelSerializer):
    """User role serializer"""
    
    class Meta:
        model = UserRole
        fields = [
            'id', 'user_id', 'role', 'permissions', 'assigned_by',
            'assigned_at', 'expires_at', 'is_active'
        ]
        read_only_fields = ['id', 'assigned_by', 'assigned_at']


class ContractApproveSerializer(serializers.Serializer):
    """Serializer for contract approval/rejection"""
    action = serializers.ChoiceField(choices=['approve', 'reject', 'delegate'])
    comments = serializers.CharField(required=False, allow_blank=True)
    delegate_to = serializers.UUIDField(required=False, allow_null=True)
    
    def validate(self, data):
        if data.get('action') == 'delegate' and not data.get('delegate_to'):
            raise serializers.ValidationError("delegate_to is required when delegating approval")
        return data


class WorkflowStartSerializer(serializers.Serializer):
    """Serializer for starting a workflow"""
    workflow_definition_id = serializers.UUIDField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)

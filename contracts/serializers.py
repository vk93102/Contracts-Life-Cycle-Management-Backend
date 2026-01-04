from rest_framework import serializers
from .models import (
    Contract, ContractVersion, ContractTemplate, Clause,
    GenerationJob, BusinessRule, ContractClause, ContractApproval,
    ContractEditHistory, WorkflowLog
)


class ContractTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractTemplate
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ClauseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clause
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ['id', 'tenant_id', 'title', 'contract_type', 'status', 'value',
                  'counterparty', 'start_date', 'end_date', 'created_by',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'tenant_id', 'created_by', 'created_at', 'updated_at']


class ContractVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractVersion
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ContractClauseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractClause
        fields = '__all__'


class ContractDetailSerializer(serializers.ModelSerializer):
    latest_version = serializers.SerializerMethodField()
    
    class Meta:
        model = Contract
        fields = ['id', 'tenant_id', 'title', 'contract_type', 'status', 'value',
                  'counterparty', 'start_date', 'end_date', 'is_approved',
                  'approved_by', 'approved_at', 'created_by', 'created_at',
                  'updated_at', 'latest_version']
        read_only_fields = ['id', 'tenant_id', 'created_by', 'created_at', 'updated_at']
    
    def get_latest_version(self, obj):
        try:
            latest = obj.versions.latest('version_number')
            return ContractVersionSerializer(latest).data
        except ContractVersion.DoesNotExist:
            return None


class GenerationJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenerationJob
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class BusinessRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessRule
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class ContractGenerateSerializer(serializers.Serializer):
    template_id = serializers.UUIDField(required=True)
    structured_inputs = serializers.JSONField(required=False, default=dict)
    user_instructions = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    selected_clauses = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )


class ContractApproveSerializer(serializers.Serializer):
    reviewed = serializers.BooleanField(required=True)
    comments = serializers.CharField(required=False, allow_blank=True)


class ContractApprovalSerializer(serializers.ModelSerializer):
    """Serializer for contract approval records"""
    approver_email = serializers.SerializerMethodField()
    
    class Meta:
        model = ContractApproval
        fields = ['id', 'contract', 'version_number', 'approver', 'approver_email',
                  'status', 'sequence', 'is_required', 'requested_at', 
                  'responded_at', 'comments']
        read_only_fields = ['id', 'requested_at', 'responded_at']
    
    def get_approver_email(self, obj):
        # This would fetch from user model - placeholder for now
        return f"user_{obj.approver}@example.com"


class ContractEditHistorySerializer(serializers.ModelSerializer):
    """Serializer for contract edit history"""
    editor_email = serializers.SerializerMethodField()
    
    class Meta:
        model = ContractEditHistory
        fields = ['id', 'contract', 'edited_by', 'editor_email', 'edited_at',
                  'changes', 'change_summary', 'version_before', 'version_after']
        read_only_fields = ['id', 'edited_at']
    
    def get_editor_email(self, obj):
        # This would fetch from user model - placeholder for now
        return f"user_{obj.edited_by}@example.com"


class WorkflowLogSerializer(serializers.ModelSerializer):
    """Serializer for workflow audit logs"""
    performer_email = serializers.SerializerMethodField()
    
    class Meta:
        model = WorkflowLog
        fields = ['id', 'contract', 'action', 'performed_by', 'performer_email',
                  'comment', 'timestamp', 'metadata']
        read_only_fields = ['id', 'timestamp']
    
    def get_performer_email(self, obj):
        # This would fetch from user model - placeholder for now
        return f"user_{obj.performed_by}@example.com"


class ContractDetailWithWorkflowSerializer(serializers.ModelSerializer):
    """Extended contract serializer with workflow information"""
    latest_version = serializers.SerializerMethodField()
    pending_approvals = serializers.SerializerMethodField()
    edit_history = ContractEditHistorySerializer(many=True, read_only=True)
    workflow_logs = WorkflowLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = Contract
        fields = ['id', 'tenant_id', 'title', 'contract_type', 'status', 'value',
                  'counterparty', 'start_date', 'end_date', 'is_approved',
                  'approved_by', 'approved_at', 'created_by', 'last_edited_by',
                  'last_edited_at', 'approval_required', 'current_approvers',
                  'approval_chain', 'document_r2_key', 'created_at', 'updated_at',
                  'latest_version', 'pending_approvals', 'edit_history', 'workflow_logs']
        read_only_fields = ['id', 'tenant_id', 'created_by', 'created_at', 'updated_at']
    
    def get_latest_version(self, obj):
        try:
            latest = obj.versions.latest('version_number')
            return ContractVersionSerializer(latest).data
        except ContractVersion.DoesNotExist:
            return None
    
    def get_pending_approvals(self, obj):
        pending = obj.approvals.filter(status='pending')
        return ContractApprovalSerializer(pending, many=True).data


class ApprovalActionSerializer(serializers.Serializer):
    """Serializer for approval actions (approve/reject)"""
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    comments = serializers.CharField(required=False, allow_blank=True, max_length=1000)

from rest_framework import serializers
from .models import (
    Contract, ContractVersion, ContractTemplate, Clause,
    GenerationJob, BusinessRule, ContractClause
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

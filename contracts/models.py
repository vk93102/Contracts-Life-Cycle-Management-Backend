"""
Contract and Workflow models with tenant isolation
"""
from django.db import models
import uuid


class ContractTemplate(models.Model):
    """
    Contract template (DOCX) with version control
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    name = models.CharField(max_length=255, help_text='Template name')
    contract_type = models.CharField(max_length=100, help_text='Type of contract (NDA, MSA, etc.)')
    description = models.TextField(blank=True, null=True, help_text='Template description')
    version = models.IntegerField(default=1, help_text='Template version number')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    r2_key = models.CharField(max_length=500, help_text='R2 storage key for DOCX template')
    merge_fields = models.JSONField(default=list, help_text='List of merge field names')
    mandatory_clauses = models.JSONField(default=list, help_text='List of mandatory clause IDs')
    business_rules = models.JSONField(default=dict, help_text='Contract-specific business rules')
    created_by = models.UUIDField(help_text='User ID who created the template')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contract_templates'
        ordering = ['-created_at']
        unique_together = [('tenant_id', 'name', 'version')]
        indexes = [
            models.Index(fields=['tenant_id', 'contract_type']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.name} v{self.version} ({self.contract_type})"


class Clause(models.Model):
    """
    Reusable contract clause with versioning and provenance
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    clause_id = models.CharField(max_length=100, help_text='Unique clause identifier (e.g., CONF-001)')
    name = models.CharField(max_length=255, help_text='Clause name')
    version = models.IntegerField(default=1, help_text='Clause version number')
    contract_type = models.CharField(max_length=100, help_text='Applicable contract type')
    content = models.TextField(help_text='Clause text content')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')
    is_mandatory = models.BooleanField(default=False, help_text='Is this clause mandatory?')
    alternatives = models.JSONField(
        default=list, 
        help_text='Alternative clause IDs with rationale and confidence: [{"clause_id": "CONF-002", "rationale": "Higher value contracts", "confidence": 0.89, "trigger_rules": {"contract_value__gte": 10000000}}]'
    )
    tags = models.JSONField(default=list, help_text='Tags for categorization')
    source_template = models.CharField(max_length=255, blank=True, null=True, help_text='Source template name')
    source_template_version = models.IntegerField(null=True, blank=True, help_text='Source template version')
    created_by = models.UUIDField(help_text='User ID who created the clause')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'clauses'
        ordering = ['-created_at']
        unique_together = [('tenant_id', 'clause_id', 'version')]
        indexes = [
            models.Index(fields=['tenant_id', 'contract_type']),
            models.Index(fields=['clause_id']),
        ]
    
    def __str__(self):
        return f"{self.clause_id} v{self.version}: {self.name}"


class Contract(models.Model):
    """
    Contract model with tenant isolation for RLS
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('executed', 'Executed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    template = models.ForeignKey(
        ContractTemplate,
        on_delete=models.PROTECT,
        related_name='contracts',
        null=True,
        blank=True,
        help_text='Source template used to generate this contract'
    )
    title = models.CharField(max_length=255, help_text='Contract title')
    current_version = models.IntegerField(default=1, help_text='Current version number')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text='Contract workflow status'
    )
    is_approved = models.BooleanField(default=False, help_text='Explicit approval flag')
    approved_by = models.UUIDField(null=True, blank=True, help_text='User ID who approved')
    approved_at = models.DateTimeField(null=True, blank=True, help_text='Approval timestamp')
    created_by = models.UUIDField(help_text='User ID who created the contract')
    counterparty = models.CharField(max_length=255, blank=True, null=True, help_text='Counterparty name')
    contract_type = models.CharField(max_length=100, blank=True, null=True, help_text='Type of contract (NDA, MSA, etc.)')
    value = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, help_text='Contract value')
    start_date = models.DateField(blank=True, null=True, help_text='Contract start date')
    end_date = models.DateField(blank=True, null=True, help_text='Contract end date')
    form_inputs = models.JSONField(default=dict, help_text='Structured intake form inputs')
    user_instructions = models.TextField(blank=True, null=True, help_text='Optional user instructions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contracts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['tenant_id', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.status})"


class ContractVersion(models.Model):
    """
    Immutable contract version with document and provenance tracking
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='versions',
        help_text='Parent contract'
    )
    version_number = models.IntegerField(help_text='Version number')
    r2_key = models.CharField(max_length=500, help_text='R2 storage key for DOCX')
    template_id = models.UUIDField(help_text='Template ID used')
    template_version = models.IntegerField(help_text='Template version used')
    change_summary = models.TextField(blank=True, null=True, help_text='Summary of changes')
    created_by = models.UUIDField(help_text='User ID who created this version')
    created_at = models.DateTimeField(auto_now_add=True)
    file_size = models.IntegerField(null=True, blank=True, help_text='File size in bytes')
    file_hash = models.CharField(max_length=64, null=True, blank=True, help_text='SHA-256 hash')
    
    class Meta:
        db_table = 'contract_versions'
        ordering = ['-version_number']
        unique_together = [('contract', 'version_number')]
        indexes = [
            models.Index(fields=['contract', 'version_number']),
        ]
    
    def __str__(self):
        return f"{self.contract.title} v{self.version_number}"


class ContractClause(models.Model):
    """
    Junction table for contract-clause relationship with provenance
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract_version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        related_name='clauses',
        help_text='Contract version this clause belongs to'
    )
    clause_id = models.CharField(max_length=100, help_text='Clause identifier')
    clause_version = models.IntegerField(help_text='Clause version used')
    clause_name = models.CharField(max_length=255, help_text='Clause name (denormalized)')
    clause_content = models.TextField(help_text='Clause content (snapshot)')
    is_mandatory = models.BooleanField(default=False, help_text='Was this clause mandatory?')
    position = models.IntegerField(help_text='Clause position in contract')
    alternatives_suggested = models.JSONField(default=list, help_text='Alternative clauses suggested')
    
    class Meta:
        db_table = 'contract_clauses'
        ordering = ['position']
        indexes = [
            models.Index(fields=['contract_version', 'position']),
            models.Index(fields=['clause_id']),
        ]
    
    def __str__(self):
        return f"{self.clause_id} v{self.clause_version} in {self.contract_version}"


class GenerationJob(models.Model):
    """
    Async contract generation job tracking
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='generation_jobs',
        null=True,
        blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0, help_text='Progress percentage (0-100)')
    error_message = models.TextField(null=True, blank=True, help_text='Error details if failed')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'generation_jobs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Job {self.id}: {self.status}"


class BusinessRule(models.Model):
    """
    Business rules for contract validation and clause suggestions
    """
    RULE_TYPE_CHOICES = [
        ('mandatory_clause', 'Mandatory Clause'),
        ('clause_suggestion', 'Clause Suggestion'),
        ('validation', 'Validation Rule'),
        ('restriction', 'Restriction Rule'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    name = models.CharField(max_length=255, help_text='Rule name')
    description = models.TextField(help_text='Rule description')
    rule_type = models.CharField(max_length=50, choices=RULE_TYPE_CHOICES, help_text='Type of rule')
    contract_types = models.JSONField(default=list, help_text='Applicable contract types (empty = all)')
    conditions = models.JSONField(help_text='Rule conditions in JSON format: {"contract_value__gte": 10000000, "contract_type": "MSA"}')
    action = models.JSONField(help_text='Action to take: {"type": "require_clause", "clause_id": "LIAB-001", "message": "Liability clause required for high-value contracts"}')
    priority = models.IntegerField(default=0, help_text='Rule priority (higher = evaluated first)')
    is_active = models.BooleanField(default=True, help_text='Is this rule active?')
    created_by = models.UUIDField(help_text='User ID who created the rule')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'business_rules'
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['tenant_id', 'rule_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.rule_type})"


class WorkflowLog(models.Model):
    """
    Audit log for contract workflow actions
    """
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('submitted', 'Submitted for Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('executed', 'Executed'),
        ('deleted', 'Deleted'),
        ('version_created', 'Version Created'),
        ('clause_added', 'Clause Added'),
        ('clause_removed', 'Clause Removed'),
        ('clause_updated', 'Clause Updated'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='workflow_logs',
        help_text='Related contract'
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text='Action performed'
    )
    performed_by = models.UUIDField(help_text='User ID who performed the action')
    comment = models.TextField(blank=True, null=True, help_text='Optional comment/reason')
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(blank=True, null=True, help_text='Additional metadata')
    
    class Meta:
        db_table = 'workflow_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['contract', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.contract.title} - {self.action} at {self.timestamp}"

"""
Contract and Workflow models with tenant isolation
"""
from django.db import models
import uuid


class ContractTemplate(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=255)
    contract_type = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    version = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    r2_key = models.CharField(max_length=500)
    merge_fields = models.JSONField(default=list)
    mandatory_clauses = models.JSONField(default=list)
    business_rules = models.JSONField(default=dict)
    created_by = models.UUIDField()
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
        return f"{self.name} v{self.version}"


class Clause(models.Model):
    """Reusable contract clause with versioning"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    clause_id = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    version = models.IntegerField(default=1)
    contract_type = models.CharField(max_length=100)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='published')
    is_mandatory = models.BooleanField(default=False)
    alternatives = models.JSONField(default=list)
    tags = models.JSONField(default=list)
    source_template = models.CharField(max_length=255, blank=True, null=True)
    source_template_version = models.IntegerField(null=True, blank=True)
    created_by = models.UUIDField()
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
        return f"{self.clause_id} v{self.version}"
    
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
    approval_chain = models.JSONField(default=dict, help_text='Approval chain configuration')
    approval_required = models.BooleanField(default=False, help_text='Is approval required?')
    current_approvers = models.JSONField(default=list, help_text='Current approvers')
    document_r2_key = models.CharField(max_length=500, blank=True, null=True, help_text='R2 storage key for document')
    last_edited_at = models.DateTimeField(blank=True, null=True, help_text='Last edited timestamp')
    last_edited_by = models.UUIDField(blank=True, null=True, help_text='User ID who last edited')
    description = models.TextField(blank=True, null=True, help_text='Contract description')
    metadata = models.JSONField(default=dict, help_text='Additional metadata')
    clauses = models.JSONField(default=list, help_text='List of contract clauses and constraints')
    signed = models.JSONField(default=dict, help_text='Signature information from SignNow with signer names')
    signed_pdf = models.BinaryField(null=True, blank=True, help_text='Signed PDF from SignNow with user signature')
    signnow_document_id = models.CharField(max_length=255, null=True, blank=True, help_text='SignNow document ID')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contracts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id', 'status']),
            models.Index(fields=['tenant_id', 'created_at']),
            models.Index(fields=['tenant_id', 'contract_type'], name='ct_tenant_type_idx'),
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

# SignNow E-Signature Models

class SignNowCredential(models.Model):
    """
    OAuth 2.0 credentials for SignNow service account (singleton)
    Stores the service account's OAuth tokens for API authentication
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # OAuth Token Fields
    access_token = models.TextField(help_text='Current OAuth access token')
    refresh_token = models.TextField(help_text='OAuth refresh token for renewing access')
    token_expires_at = models.DateTimeField(help_text='When the access token expires')
    
    # Service Account Identity
    client_id = models.CharField(max_length=500, help_text='SignNow OAuth client ID')
    client_secret = models.CharField(max_length=500, help_text='SignNow OAuth client secret')
    account_name = models.CharField(max_length=255, help_text='Service account display name')
    account_id = models.CharField(max_length=255, help_text='SignNow service account ID')
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True, help_text='Last token refresh time')
    
    class Meta:
        db_table = 'signnow_credentials'
        verbose_name_plural = 'SignNow Credentials'
    
    def __str__(self):
        return f"SignNow Service Account: {self.account_name}"


class ESignatureContract(models.Model):
    """
    Maps a CLM Contract to a SignNow document for e-signature workflow
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent for Signature'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('declined', 'Declined'),
    ]
    
    SIGNING_ORDER_CHOICES = [
        ('sequential', 'Sequential'),
        ('parallel', 'Parallel'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name='esignature_contract',
        help_text='Associated CLM contract'
    )
    
    # SignNow Document Reference
    signnow_document_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text='SignNow document ID'
    )
    
    # Signing Workflow
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True,
        help_text='Current signing status'
    )
    signing_order = models.CharField(
        max_length=20,
        choices=SIGNING_ORDER_CHOICES,
        default='parallel',
        help_text='Sequential or parallel signing'
    )
    
    # Timeline
    sent_at = models.DateTimeField(null=True, blank=True, help_text='When sent for signature')
    completed_at = models.DateTimeField(null=True, blank=True, help_text='When all signers completed')
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Signing deadline')
    last_status_check_at = models.DateTimeField(null=True, blank=True, help_text='Last status polling time')
    
    # Storage References
    original_r2_key = models.CharField(
        max_length=500,
        help_text='Original contract PDF in R2'
    )
    executed_r2_key = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text='Signed contract PDF in R2'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'esignature_contracts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['signnow_document_id']),
            models.Index(fields=['status']),
            models.Index(fields=['contract', 'status']),
        ]
    
    def __str__(self):
        return f"ESignature: {self.contract.title} ({self.status})"


class Signer(models.Model):
    """
    Email-based signer for an e-signature contract
    Signers are identified by email, not user accounts
    """
    STATUS_CHOICES = [
        ('invited', 'Invited'),
        ('viewed', 'Viewed'),
        ('in_progress', 'In Progress'),
        ('signed', 'Signed'),
        ('declined', 'Declined'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    esignature_contract = models.ForeignKey(
        ESignatureContract,
        on_delete=models.CASCADE,
        related_name='signers',
        help_text='Associated e-signature contract'
    )
    
    # Signer Identity (Email-based, no user account)
    email = models.EmailField(help_text='Signer email address')
    name = models.CharField(max_length=255, help_text='Signer full name')
    
    # Signing Order
    signing_order = models.IntegerField(help_text='Order in signing sequence (1-based)')
    
    # Status Tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='invited',
        db_index=True,
        help_text='Current signing status'
    )
    has_signed = models.BooleanField(default=False, help_text='Whether signer completed')
    signed_at = models.DateTimeField(null=True, blank=True, help_text='When signer completed')
    
    # Signing URL Management
    signing_url = models.TextField(null=True, blank=True, help_text='Embedded signing URL')
    signing_url_expires_at = models.DateTimeField(null=True, blank=True, help_text='URL expiration (24h)')
    
    # Decline Tracking
    declined_reason = models.TextField(null=True, blank=True, help_text='Reason if declined')
    
    # Metadata
    invited_at = models.DateTimeField(auto_now_add=True, help_text='When invitation sent')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'signers'
        ordering = ['signing_order', 'email']
        unique_together = [('esignature_contract', 'email')]
        indexes = [
            models.Index(fields=['esignature_contract', 'status']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.email} ({self.status}) - {self.esignature_contract.contract.title}"


class SigningAuditLog(models.Model):
    """
    Immutable audit trail of all e-signature events
    """
    EVENT_CHOICES = [
        ('invite_sent', 'Invitation Sent'),
        ('document_viewed', 'Document Viewed'),
        ('signing_started', 'Signing Started'),
        ('signing_completed', 'Signing Completed'),
        ('signing_declined', 'Signing Declined'),
        ('status_checked', 'Status Checked'),
        ('document_downloaded', 'Document Downloaded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    esignature_contract = models.ForeignKey(
        ESignatureContract,
        on_delete=models.CASCADE,
        related_name='audit_logs',
        help_text='Associated e-signature contract'
    )
    signer = models.ForeignKey(
        Signer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='Associated signer (if applicable)'
    )
    
    # Event Details
    event = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES,
        db_index=True,
        help_text='Event type'
    )
    message = models.TextField(help_text='Event description')
    
    # Status Transitions
    old_status = models.CharField(max_length=20, null=True, blank=True, help_text='Previous status')
    new_status = models.CharField(max_length=20, null=True, blank=True, help_text='New status')
    
    # SignNow Response
    signnow_response = models.JSONField(
        default=dict,
        null=True,
        blank=True,
        help_text='Full SignNow API response'
    )

    # Timestamp (immutable)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'signing_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['esignature_contract', 'created_at']),
            models.Index(fields=['event', 'created_at']),
        ]
        permissions = [
            ('view_signing_audit_log', 'Can view signing audit logs'),
        ]

    def __str__(self):
        return f"{self.event} - {self.esignature_contract.contract.title} at {self.created_at}"


# ==========================================================================
# Firma E-Sign Models (separate provider)
# ==========================================================================


class FirmaSignatureContract(models.Model):
    """Maps a CLM Contract to a Firma document/envelope for e-sign workflow."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent for Signature'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('declined', 'Declined'),
        ('failed', 'Failed'),
    ]

    SIGNING_ORDER_CHOICES = [
        ('sequential', 'Sequential'),
        ('parallel', 'Parallel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name='firma_signature_contract',
        help_text='Associated CLM contract',
    )

    firma_document_id = models.CharField(max_length=255, unique=True, db_index=True, help_text='Firma document/envelope ID')

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='draft', db_index=True)
    signing_order = models.CharField(max_length=20, choices=SIGNING_ORDER_CHOICES, default='sequential')

    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_status_check_at = models.DateTimeField(null=True, blank=True)

    original_r2_key = models.CharField(max_length=500, help_text='Original contract PDF in R2')
    executed_r2_key = models.CharField(max_length=500, null=True, blank=True, help_text='Signed contract PDF in R2')

    signing_request_data = models.JSONField(default=dict, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'firma_signature_contracts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['firma_document_id'], name='firma_sc_docid_idx'),
            models.Index(fields=['status'], name='firma_sc_status_idx'),
            models.Index(fields=['contract', 'status'], name='firma_sc_contract_status_idx'),
        ]

    def __str__(self):
        return f"FirmaSignature: {self.contract.title} ({self.status})"


class FirmaSigner(models.Model):
    STATUS_CHOICES = [
        ('invited', 'Invited'),
        ('viewed', 'Viewed'),
        ('in_progress', 'In Progress'),
        ('signed', 'Signed'),
        ('declined', 'Declined'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firma_signature_contract = models.ForeignKey(
        FirmaSignatureContract,
        on_delete=models.CASCADE,
        related_name='signers',
    )

    email = models.EmailField()
    name = models.CharField(max_length=255)
    signing_order = models.IntegerField(help_text='Order in signing sequence (1-based)')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='invited', db_index=True)
    has_signed = models.BooleanField(default=False)
    signed_at = models.DateTimeField(null=True, blank=True)

    signing_url = models.TextField(null=True, blank=True)
    signing_url_expires_at = models.DateTimeField(null=True, blank=True)

    declined_reason = models.TextField(null=True, blank=True)

    invited_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'firma_signers'
        ordering = ['signing_order', 'email']
        unique_together = [('firma_signature_contract', 'email')]
        indexes = [
            models.Index(fields=['firma_signature_contract', 'status'], name='firma_signer_sc_status_idx'),
            models.Index(fields=['email'], name='firma_signer_email_idx'),
        ]

    def __str__(self):
        return f"{self.email} ({self.status}) - {self.firma_signature_contract.contract.title}"


class FirmaSigningAuditLog(models.Model):
    EVENT_CHOICES = [
        ('upload', 'Document Uploaded'),
        ('invite_sent', 'Invitation Sent'),
        ('status_checked', 'Status Checked'),
        ('document_downloaded', 'Document Downloaded'),
        ('webhook', 'Webhook Event'),
        ('reminder', 'Reminder'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    firma_signature_contract = models.ForeignKey(
        FirmaSignatureContract,
        on_delete=models.CASCADE,
        related_name='audit_logs',
    )
    signer = models.ForeignKey(
        FirmaSigner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )

    event = models.CharField(max_length=50, choices=EVENT_CHOICES, db_index=True)
    message = models.TextField()
    old_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20, null=True, blank=True)

    firma_response = models.JSONField(default=dict, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'firma_signing_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['firma_signature_contract', 'created_at'], name='firma_audit_sc_created_idx'),
            models.Index(fields=['event', 'created_at'], name='firma_audit_event_created_idx'),
        ]

    def __str__(self):
        title = getattr(self.firma_signature_contract.contract, 'title', '')
        return f"{self.event} - {title} at {self.created_at}"


# ========== MANUAL EDITING MODELS ==========

class ContractEditingSession(models.Model):
    """
    Track user's contract editing session
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    user_id = models.UUIDField()
    template_id = models.UUIDField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    form_data = models.JSONField(default=dict, help_text='User-filled form data')
    selected_clause_ids = models.JSONField(default=list, help_text='User-selected clause IDs')
    custom_clauses = models.JSONField(default=dict, help_text='Custom clause content by user')
    constraints_config = models.JSONField(default=dict, help_text='Constraint/version definitions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_saved_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'contract_editing_sessions'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['tenant_id', 'user_id']),
            models.Index(fields=['status', 'updated_at']),
        ]
    
    def __str__(self):
        return f"Session {self.id[:8]} - {self.status}"


class ContractEditingStep(models.Model):
    """
    Track each step of contract editing for audit and recovery
    """
    STEP_TYPES = [
        ('template_selection', 'Template Selected'),
        ('form_fill', 'Form Field Filled'),
        ('clause_selection', 'Clause Selected'),
        ('clause_removal', 'Clause Removed'),
        ('clause_customization', 'Clause Customized'),
        ('constraint_definition', 'Constraint Defined'),
        ('preview_generated', 'Preview Generated'),
        ('field_edited', 'Field Edited After Preview'),
        ('saved', 'Draft Saved'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ContractEditingSession,
        on_delete=models.CASCADE,
        related_name='steps'
    )
    step_type = models.CharField(max_length=30, choices=STEP_TYPES)
    step_data = models.JSONField(help_text='Data for this step')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'contract_editing_steps'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.session.id[:8]} - {self.step_type}"


class ContractEditingTemplate(models.Model):
    """
    Extended template for manual editing with form field definitions
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_template_id = models.UUIDField(help_text='ID of base ContractTemplate')
    tenant_id = models.UUIDField(db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, default='general')
    contract_type = models.CharField(max_length=100)
    
    # Form Field Configuration
    form_fields = models.JSONField(
        default=dict,
        help_text="""Form field definitions like:
        {
            "party_a_name": {
                "label": "Your Company Name",
                "type": "text",
                "required": true,
                "placeholder": "Enter your company name",
                "validation": {"min_length": 2, "max_length": 255}
            },
            "party_b_name": {
                "label": "Counterparty Name",
                "type": "text",
                "required": true
            },
            "contract_value": {
                "label": "Contract Value (USD)",
                "type": "number",
                "required": true,
                "min": 0,
                "max": 999999999
            }
        }"""
    )
    
    # Default form values
    default_values = models.JSONField(default=dict, help_text='Default values for form fields')
    
    # Clause configuration
    mandatory_clauses = models.JSONField(default=list, help_text='List of mandatory clause IDs')
    optional_clauses = models.JSONField(default=list, help_text='List of optional clause IDs')
    clause_order = models.JSONField(default=list, help_text='Suggested clause order')
    
    # Constraint templates
    constraint_templates = models.JSONField(
        default=dict,
        help_text="""Predefined constraints users can apply:
        {
            "payment_terms": {
                "label": "Payment Terms",
                "options": ["Net 30", "Net 60", "Net 90", "Immediate"],
                "default": "Net 30"
            },
            "jurisdiction": {
                "label": "Governing Jurisdiction",
                "options": ["California", "New York", "Delaware", "Federal"],
                "default": "California"
            }
        }"""
    )
    
    # Contract content template
    contract_content_template = models.TextField(
        help_text='Base contract template with {{placeholders}} for form fields'
    )
    
    # Professional styling
    styling_config = models.JSONField(
        default=dict,
        help_text='Professional styling for generated contracts'
    )
    
    preview_sample = models.TextField(blank=True, help_text='Sample preview of contract')
    
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contract_editing_templates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['contract_type']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.contract_type})"


class ContractPreview(models.Model):
    """
    Store generated contract previews
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        ContractEditingSession,
        on_delete=models.CASCADE,
        related_name='preview'
    )
    preview_html = models.TextField(help_text='HTML preview of contract')
    preview_text = models.TextField(help_text='Plain text version of contract')
    generated_at = models.DateTimeField(auto_now_add=True)
    form_data_snapshot = models.JSONField(help_text='Snapshot of form data used for preview')
    clauses_snapshot = models.JSONField(help_text='Snapshot of selected clauses')
    constraints_snapshot = models.JSONField(help_text='Snapshot of constraints used')
    
    class Meta:
        db_table = 'contract_previews'
        indexes = [
            models.Index(fields=['session']),
        ]
    
    def __str__(self):
        return f"Preview for session {self.session.id[:8]}"


class ContractFieldValidationRule(models.Model):
    """
    Define validation rules for contract fields
    """
    RULE_TYPES = [
        ('regex', 'Regular Expression'),
        ('min_value', 'Minimum Value'),
        ('max_value', 'Maximum Value'),
        ('length', 'String Length'),
        ('custom', 'Custom Validation'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(
        ContractEditingTemplate,
        on_delete=models.CASCADE,
        related_name='field_validations'
    )
    field_name = models.CharField(max_length=255)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPES)
    rule_value = models.JSONField(help_text='Rule configuration')
    error_message = models.CharField(max_length=500)
    
    class Meta:
        db_table = 'contract_field_validation_rules'
        unique_together = [('template', 'field_name', 'rule_type')]
    
    def __str__(self):
        return f"{self.field_name} - {self.rule_type}"


class ContractEdits(models.Model):
    """
    Track edits made after preview
    """
    EDIT_TYPES = [
        ('form_field', 'Form Field Edited'),
        ('clause_added', 'Clause Added'),
        ('clause_removed', 'Clause Removed'),
        ('clause_content_edited', 'Clause Content Edited'),
        ('constraint_added', 'Constraint Added'),
        ('constraint_modified', 'Constraint Modified'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ContractEditingSession,
        on_delete=models.CASCADE,
        related_name='edits'
    )
    edit_type = models.CharField(max_length=30, choices=EDIT_TYPES)
    field_name = models.CharField(max_length=255, blank=True)
    old_value = models.JSONField(blank=True, null=True)
    new_value = models.JSONField(blank=True, null=True)
    edit_reason = models.TextField(blank=True, help_text='Why the user made this edit')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'contract_edits'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['session', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.session.id[:8]} - {self.edit_type}"

"""
Workflow engine models for contract lifecycle management
Production-ready implementation with multi-level approval, SLA tracking, and notifications
"""
from django.db import models
from django.utils import timezone
import uuid


class WorkflowDefinition(models.Model):
    """
    Configurable workflow definitions for different contract types
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    name = models.CharField(max_length=255, help_text='Workflow name (e.g., "High Value Contract Approval")')
    description = models.TextField(blank=True, null=True, help_text='Workflow description')
    contract_types = models.JSONField(default=list, help_text='Applicable contract types (empty = all)')
    trigger_conditions = models.JSONField(
        default=dict,
        help_text='Conditions that trigger this workflow: {"contract_value__gte": 100000, "contract_type": "MSA"}'
    )
    stages = models.JSONField(
        default=list,
        help_text='Workflow stages configuration: [{"stage_name": "Legal Review", "sequence": 1, "approvers": ["role:legal"], "parallel": false, "sla_hours": 48}]'
    )
    is_active = models.BooleanField(default=True, help_text='Is this workflow active?')
    priority = models.IntegerField(default=0, help_text='Workflow priority (higher = selected first)')
    created_by = models.UUIDField(help_text='User ID who created this workflow')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'workflow_definitions'
        ordering = ['-priority', 'name']
        indexes = [
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['priority']),
        ]
    
    def __str__(self):
        return f"{self.name} (Priority: {self.priority})"


class WorkflowInstance(models.Model):
    """
    Active workflow instance for a contract
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(
        'contracts.Contract',
        on_delete=models.CASCADE,
        related_name='workflow_instances',
        help_text='Associated contract'
    )
    workflow_definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.PROTECT,
        related_name='instances',
        help_text='Workflow definition used'
    )
    current_stage = models.IntegerField(default=0, help_text='Current stage sequence number')
    current_stage_name = models.CharField(max_length=255, help_text='Current stage name')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, help_text='Additional workflow metadata')
    
    class Meta:
        db_table = 'workflow_instances'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['contract', 'status']),
            models.Index(fields=['status', 'started_at']),
        ]
    
    def __str__(self):
        return f"Workflow for {self.contract.title} - Stage: {self.current_stage_name}"


class WorkflowStageApproval(models.Model):
    """
    Individual approval within a workflow stage
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('delegated', 'Delegated'),
        ('expired', 'Expired'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name='stage_approvals',
        help_text='Parent workflow instance'
    )
    stage_sequence = models.IntegerField(help_text='Stage sequence number')
    stage_name = models.CharField(max_length=255, help_text='Stage name')
    approver = models.UUIDField(help_text='User ID of approver')
    approver_role = models.CharField(max_length=100, blank=True, null=True, help_text='Approver role (if role-based)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_required = models.BooleanField(default=True, help_text='Is this approval mandatory?')
    requested_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField(null=True, blank=True, help_text='SLA deadline')
    responded_at = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True, null=True)
    delegated_to = models.UUIDField(null=True, blank=True, help_text='User ID if delegated')
    delegation_reason = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'workflow_stage_approvals'
        ordering = ['stage_sequence', 'requested_at']
        indexes = [
            models.Index(fields=['workflow_instance', 'stage_sequence']),
            models.Index(fields=['approver', 'status']),
            models.Index(fields=['status', 'due_at']),
        ]
    
    def __str__(self):
        return f"{self.stage_name} - {self.approver} ({self.status})"
    
    def is_overdue(self):
        """Check if approval is overdue"""
        if self.due_at and self.status == 'pending':
            return timezone.now() > self.due_at
        return False


class SLARule(models.Model):
    """
    SLA (Service Level Agreement) rules for workflow stages
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    name = models.CharField(max_length=255, help_text='SLA rule name')
    description = models.TextField(blank=True, null=True)
    workflow_definition = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name='sla_rules',
        null=True,
        blank=True,
        help_text='Specific workflow (null = applies to all)'
    )
    stage_name = models.CharField(max_length=255, blank=True, null=True, help_text='Specific stage (null = applies to all)')
    sla_hours = models.IntegerField(help_text='SLA time in hours')
    escalation_enabled = models.BooleanField(default=True, help_text='Enable escalation on breach')
    escalation_users = models.JSONField(default=list, help_text='User IDs to notify on escalation')
    escalation_message = models.TextField(blank=True, null=True, help_text='Custom escalation message')
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField(help_text='User ID who created this rule')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sla_rules'
        ordering = ['sla_hours']
        indexes = [
            models.Index(fields=['tenant_id', 'is_active']),
            models.Index(fields=['workflow_definition', 'stage_name']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.sla_hours}h"


class SLABreach(models.Model):
    """
    Track SLA breaches for reporting and analytics
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('resolved', 'Resolved'),
        ('acknowledged', 'Acknowledged'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        related_name='sla_breaches',
        help_text='Workflow instance with breach'
    )
    stage_approval = models.ForeignKey(
        WorkflowStageApproval,
        on_delete=models.CASCADE,
        related_name='sla_breaches',
        help_text='Specific approval with breach'
    )
    sla_rule = models.ForeignKey(
        SLARule,
        on_delete=models.SET_NULL,
        null=True,
        help_text='SLA rule that was breached'
    )
    breach_time = models.DateTimeField(auto_now_add=True)
    expected_completion = models.DateTimeField(help_text='When it should have been completed')
    actual_completion = models.DateTimeField(null=True, blank=True, help_text='When actually completed')
    breach_duration_hours = models.FloatField(help_text='How many hours overdue')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    escalated = models.BooleanField(default=False, help_text='Has this been escalated?')
    escalation_sent_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'sla_breaches'
        ordering = ['-breach_time']
        indexes = [
            models.Index(fields=['status', 'breach_time']),
            models.Index(fields=['workflow_instance', 'status']),
        ]
    
    def __str__(self):
        return f"SLA Breach: {self.workflow_instance.contract.title} - {self.breach_duration_hours}h overdue"


class NotificationQueue(models.Model):
    """
    Notification queue for email and in-app notifications
    """
    TYPE_CHOICES = [
        ('email', 'Email'),
        ('in_app', 'In-App'),
        ('both', 'Both'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.UUIDField(help_text='User ID of recipient')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='both')
    subject = models.CharField(max_length=255, help_text='Notification subject')
    message = models.TextField(help_text='Notification message body')
    contract = models.ForeignKey(
        'contracts.Contract',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text='Related contract (if any)'
    )
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text='Related workflow (if any)'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.IntegerField(default=0, help_text='Priority (higher = sent first)')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, help_text='For in-app notifications')
    error_message = models.TextField(blank=True, null=True, help_text='Error details if failed')
    metadata = models.JSONField(default=dict, help_text='Additional metadata (links, actions, etc.)')
    
    class Meta:
        db_table = 'notification_queue'
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"Notification to {self.recipient}: {self.subject}"


class AuditLog(models.Model):
    """
    Comprehensive audit log for all system activities
    """
    ACTION_CHOICES = [
        # Contract actions
        ('contract_created', 'Contract Created'),
        ('contract_updated', 'Contract Updated'),
        ('contract_deleted', 'Contract Deleted'),
        ('contract_viewed', 'Contract Viewed'),
        ('contract_exported', 'Contract Exported'),
        ('contract_imported', 'Contract Imported'),
        
        # Workflow actions
        ('workflow_started', 'Workflow Started'),
        ('workflow_completed', 'Workflow Completed'),
        ('workflow_cancelled', 'Workflow Cancelled'),
        ('approval_requested', 'Approval Requested'),
        ('approval_approved', 'Approval Approved'),
        ('approval_rejected', 'Approval Rejected'),
        ('approval_delegated', 'Approval Delegated'),
        
        # Template/Clause actions
        ('template_created', 'Template Created'),
        ('template_updated', 'Template Updated'),
        ('clause_created', 'Clause Created'),
        ('clause_updated', 'Clause Updated'),
        
        # Admin actions
        ('user_login', 'User Login'),
        ('user_logout', 'User Logout'),
        ('role_assigned', 'Role Assigned'),
        ('settings_changed', 'Settings Changed'),
        ('sla_rule_created', 'SLA Rule Created'),
        ('sla_rule_updated', 'SLA Rule Updated'),
        
        # SLA actions
        ('sla_breach', 'SLA Breach'),
        ('sla_escalation', 'SLA Escalation'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    user_id = models.UUIDField(help_text='User who performed the action')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, help_text='Action performed')
    resource_type = models.CharField(max_length=50, help_text='Type of resource (contract, template, etc.)')
    resource_id = models.UUIDField(help_text='ID of the affected resource')
    contract = models.ForeignKey(
        'contracts.Contract',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='Related contract'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text='User IP address')
    user_agent = models.TextField(blank=True, null=True, help_text='User agent string')
    changes = models.JSONField(default=dict, help_text='Details of changes made')
    metadata = models.JSONField(default=dict, help_text='Additional context')
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tenant_id', 'timestamp']),
            models.Index(fields=['user_id', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['contract', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
    
    def __str__(self):
        return f"{self.action} by {self.user_id} at {self.timestamp}"


class UserRole(models.Model):
    """
    Role-based access control for users
    """
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('legal', 'Legal Team'),
        ('sales', 'Sales Team'),
        ('finance', 'Finance Team'),
        ('manager', 'Manager'),
        ('user', 'Standard User'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    user_id = models.UUIDField(help_text='User ID')
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, help_text='User role')
    permissions = models.JSONField(
        default=list,
        help_text='Specific permissions: ["approve_contracts", "create_templates", "view_audit_logs"]'
    )
    assigned_by = models.UUIDField(help_text='User ID who assigned this role')
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Role expiration (null = no expiration)')
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'user_roles'
        ordering = ['user_id', 'role']
        unique_together = [('tenant_id', 'user_id', 'role')]
        indexes = [
            models.Index(fields=['tenant_id', 'user_id']),
            models.Index(fields=['role', 'is_active']),
        ]
    
    def __str__(self):
        return f"User {self.user_id} - Role: {self.role}"

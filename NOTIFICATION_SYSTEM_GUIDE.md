# 📧 Notification System Implementation Guide

## Overview
This guide provides a complete implementation plan for adding a notification system to your CLM backend for approval workflows, contract updates, and system events.

---

## 🏗️ Architecture Options

### **Option 1: Django Signals + Email (Recommended for MVP)**
Simple, reliable, synchronous email notifications.

### **Option 2: Django Signals + Celery + Multi-Channel**
Production-ready async notifications (email, SMS, in-app, Slack).

### **Option 3: Real-time WebSocket Notifications**
For live dashboard updates using Django Channels.

---

## 📋 Implementation Steps

### **Phase 1: Database Models (Week 1)**

#### 1.1 Create Notification Model

Add to `contracts/models.py`:

```python
class Notification(models.Model):
    """
    User notifications for contract events
    """
    NOTIFICATION_TYPES = [
        ('approval_request', 'Approval Request'),
        ('contract_approved', 'Contract Approved'),
        ('contract_rejected', 'Contract Rejected'),
        ('contract_updated', 'Contract Updated'),
        ('contract_expiring', 'Contract Expiring Soon'),
        ('mention', 'Mentioned in Comment'),
    ]
    
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('in_app', 'In-App'),
        ('sms', 'SMS'),
        ('slack', 'Slack'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, help_text='Tenant ID for RLS')
    recipient = models.UUIDField(help_text='User ID of notification recipient')
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='in_app')
    title = models.CharField(max_length=255, help_text='Notification title')
    message = models.TextField(help_text='Notification message body')
    
    # Related objects
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True
    )
    
    # Status tracking
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    
    # Metadata
    action_url = models.CharField(max_length=500, blank=True, null=True, help_text='URL for notification action')
    metadata = models.JSONField(default=dict, help_text='Additional notification data')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant_id', 'recipient', 'is_read']),
            models.Index(fields=['notification_type']),
        ]
    
    def __str__(self):
        return f"{self.notification_type} for {self.recipient}"


class NotificationPreference(models.Model):
    """
    User preferences for notification channels and types
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(unique=True, help_text='User ID')
    tenant_id = models.UUIDField(db_index=True)
    
    # Channel preferences
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    slack_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)
    
    # Event preferences (JSON for flexibility)
    preferences = models.JSONField(
        default=dict,
        help_text='Event-specific preferences: {"approval_request": {"email": true, "sms": false}}'
    )
    
    # Contact info
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    slack_user_id = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'notification_preferences'
    
    def __str__(self):
        return f"Preferences for {self.user_id}"
```

#### 1.2 Create Migration

```bash
python manage.py makemigrations contracts
python manage.py migrate contracts
```

---

### **Phase 2: Notification Service (Week 1-2)**

#### 2.1 Create `contracts/notifications.py`

```python
"""
Notification service for contract events
"""
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import Notification, NotificationPreference, Contract
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Centralized notification service
    """
    
    @staticmethod
    def create_notification(
        tenant_id,
        recipient_id,
        notification_type,
        title,
        message,
        contract=None,
        action_url=None,
        metadata=None
    ):
        """
        Create and send notification
        """
        # Get user preferences
        try:
            prefs = NotificationPreference.objects.get(user_id=recipient_id)
        except NotificationPreference.DoesNotExist:
            # Use defaults
            prefs = NotificationPreference(
                user_id=recipient_id,
                tenant_id=tenant_id
            )
        
        # Determine channels to use
        channels = []
        if prefs.in_app_enabled:
            channels.append('in_app')
        if prefs.email_enabled:
            channels.append('email')
        
        # Create notifications for each channel
        notifications = []
        for channel in channels:
            notification = Notification.objects.create(
                tenant_id=tenant_id,
                recipient=recipient_id,
                notification_type=notification_type,
                channel=channel,
                title=title,
                message=message,
                contract=contract,
                action_url=action_url,
                metadata=metadata or {}
            )
            notifications.append(notification)
            
            # Send immediately based on channel
            if channel == 'email':
                NotificationService._send_email(notification)
            # Add other channels here
        
        return notifications
    
    @staticmethod
    def _send_email(notification):
        """
        Send email notification
        """
        # TODO: Get user email from user service
        recipient_email = f"user_{notification.recipient}@example.com"
        
        try:
            send_mail(
                subject=notification.title,
                message=notification.message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient_email],
                fail_silently=False,
            )
            notification.sent_at = timezone.now()
            notification.save()
            logger.info(f"Email sent for notification {notification.id}")
        except Exception as e:
            notification.failed = True
            notification.error_message = str(e)
            notification.save()
            logger.error(f"Failed to send email for notification {notification.id}: {e}")
    
    @staticmethod
    def notify_approval_request(contract, approver_id):
        """
        Notify user of approval request
        """
        return NotificationService.create_notification(
            tenant_id=contract.tenant_id,
            recipient_id=approver_id,
            notification_type='approval_request',
            title=f'Approval Required: {contract.title}',
            message=f'You have been requested to review and approve the contract "{contract.title}".',
            contract=contract,
            action_url=f'/contracts/{contract.id}/approve',
            metadata={
                'contract_id': str(contract.id),
                'contract_type': contract.contract_type,
            }
        )
    
    @staticmethod
    def notify_contract_approved(contract, approver_id):
        """
        Notify contract creator of approval
        """
        return NotificationService.create_notification(
            tenant_id=contract.tenant_id,
            recipient_id=contract.created_by,
            notification_type='contract_approved',
            title=f'Contract Approved: {contract.title}',
            message=f'Your contract "{contract.title}" has been approved.',
            contract=contract,
            action_url=f'/contracts/{contract.id}',
            metadata={
                'contract_id': str(contract.id),
                'approved_by': str(approver_id),
            }
        )
    
    @staticmethod
    def notify_contract_rejected(contract, approver_id, reason=''):
        """
        Notify contract creator of rejection
        """
        message = f'Your contract "{contract.title}" has been rejected.'
        if reason:
            message += f'\n\nReason: {reason}'
        
        return NotificationService.create_notification(
            tenant_id=contract.tenant_id,
            recipient_id=contract.created_by,
            notification_type='contract_rejected',
            title=f'Contract Rejected: {contract.title}',
            message=message,
            contract=contract,
            action_url=f'/contracts/{contract.id}',
            metadata={
                'contract_id': str(contract.id),
                'rejected_by': str(approver_id),
                'reason': reason,
            }
        )
    
    @staticmethod
    def notify_contract_updated(contract, editor_id):
        """
        Notify approvers/stakeholders of contract updates
        """
        # Notify all current approvers
        notifications = []
        for approver_id in contract.current_approvers:
            if approver_id != editor_id:  # Don't notify the editor
                notif = NotificationService.create_notification(
                    tenant_id=contract.tenant_id,
                    recipient_id=approver_id,
                    notification_type='contract_updated',
                    title=f'Contract Updated: {contract.title}',
                    message=f'The contract "{contract.title}" has been updated.',
                    contract=contract,
                    action_url=f'/contracts/{contract.id}',
                    metadata={
                        'contract_id': str(contract.id),
                        'edited_by': str(editor_id),
                    }
                )
                notifications.extend(notif)
        
        return notifications
```

---

### **Phase 3: Integration with Workflow (Week 2)**

#### 3.1 Update `contracts/admin_views.py`

Add notification triggers to approval workflow:

```python
from .notifications import NotificationService

# In AdminContractViewSet.create():
# After creating approval records:
for approver_id in approver_list:
    ContractApproval.objects.create(...)
    # Send notification
    NotificationService.notify_approval_request(contract, approver_id)

# In ApprovalActionView.post():
# After approval:
if action_type == 'approve':
    # ... existing code ...
    if pending_count == 0:
        # All approved
        contract.status = 'approved'
        contract.save()
        NotificationService.notify_contract_approved(contract, request.user.user_id)
else:
    # Rejection
    contract.status = 'rejected'
    contract.save()
    NotificationService.notify_contract_rejected(
        contract, 
        request.user.user_id,
        comments
    )

# In AdminContractViewSet.update():
# After updating:
if changes:
    # ... existing code ...
    NotificationService.notify_contract_updated(contract, request.user.user_id)
```

---

### **Phase 4: API Endpoints (Week 2)**

#### 4.1 Create `contracts/notification_views.py`

```python
"""
Notification API endpoints
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user notifications
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user.user_id,
            channel='in_app'
        ).select_related('contract')
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        return Response({'status': 'marked_read'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        count = self.get_queryset().filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return Response({'marked_read': count})


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for notification preferences
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationPreferenceSerializer
    
    def get_queryset(self):
        return NotificationPreference.objects.filter(
            user_id=self.request.user.user_id
        )
    
    def get_object(self):
        """Get or create preference for current user"""
        obj, created = NotificationPreference.objects.get_or_create(
            user_id=self.request.user.user_id,
            defaults={'tenant_id': self.request.user.tenant_id}
        )
        return obj
```

#### 4.2 Add to URL configuration

```python
# contracts/urls_admin.py
from .notification_views import NotificationViewSet, NotificationPreferenceViewSet

router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'notification-preferences', NotificationPreferenceViewSet, basename='notification-preference')
```

---

### **Phase 5: Email Templates (Week 2)**

#### 5.1 Create `contracts/templates/emails/`

**approval_request.html:**
```html
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .button { background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; }
        .header { background: #f8f9fa; padding: 20px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Approval Required</h2>
        </div>
        <p>Hello,</p>
        <p>You have been requested to review and approve the following contract:</p>
        <ul>
            <li><strong>Title:</strong> {{ contract.title }}</li>
            <li><strong>Type:</strong> {{ contract.contract_type }}</li>
            <li><strong>Value:</strong> ${{ contract.value }}</li>
        </ul>
        <p>
            <a href="{{ action_url }}" class="button">Review Contract</a>
        </p>
        <p>Please review the contract and take appropriate action.</p>
    </div>
</body>
</html>
```

---

### **Phase 6: Celery Integration (Production - Week 3)**

#### 6.1 Install Celery

```bash
pip install celery redis
```

#### 6.2 Create `clm_backend/celery.py`

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clm_backend.settings')

app = Celery('clm_backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

#### 6.3 Create `contracts/tasks.py`

```python
from celery import shared_task
from .notifications import NotificationService
from .models import Contract
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_approval_notification(contract_id, approver_id):
    """Async task to send approval notification"""
    try:
        contract = Contract.objects.get(id=contract_id)
        NotificationService.notify_approval_request(contract, approver_id)
        logger.info(f"Approval notification sent for contract {contract_id}")
    except Exception as e:
        logger.error(f"Failed to send approval notification: {e}")


@shared_task
def check_expiring_contracts():
    """Daily task to check for expiring contracts"""
    from django.utils import timezone
    from datetime import timedelta
    
    threshold = timezone.now().date() + timedelta(days=30)
    expiring = Contract.objects.filter(
        end_date__lte=threshold,
        end_date__gte=timezone.now().date(),
        status='executed'
    )
    
    for contract in expiring:
        # Notify contract owner
        NotificationService.create_notification(
            tenant_id=contract.tenant_id,
            recipient_id=contract.created_by,
            notification_type='contract_expiring',
            title=f'Contract Expiring: {contract.title}',
            message=f'Your contract "{contract.title}" is expiring in {(contract.end_date - timezone.now().date()).days} days.',
            contract=contract,
            action_url=f'/contracts/{contract.id}'
        )
```

#### 6.4 Update `clm_backend/settings.py`

```python
# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Email Configuration (for production)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # or your SMTP server
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'noreply@yourclm.com'
```

---

## 🚀 Deployment Steps

### **1. Development Testing**
```bash
# Start Django
python manage.py runserver 4000

# Test notifications appear in-app
# Test email sending (use console backend initially)
```

### **2. Production Deployment**
```bash
# Install Redis
brew install redis  # macOS
redis-server

# Start Celery worker
celery -A clm_backend worker -l info

# Start Celery beat (for scheduled tasks)
celery -A clm_backend beat -l info
```

---

## 📊 Frontend Integration

### **API Endpoints Available:**

```
GET  /api/admin/notifications/              # List notifications
GET  /api/admin/notifications/unread_count/ # Get unread count
POST /api/admin/notifications/{id}/mark_read/  # Mark as read
POST /api/admin/notifications/mark_all_read/   # Mark all read

GET  /api/admin/notification-preferences/   # Get preferences
PUT  /api/admin/notification-preferences/{id}/  # Update preferences
```

### **Frontend Example (React):**

```javascript
// Fetch unread notifications
const fetchNotifications = async () => {
  const response = await fetch('/api/admin/notifications/unread_count/', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  const data = await response.json();
  setBadgeCount(data.unread_count);
};

// Poll every 30 seconds
useEffect(() => {
  const interval = setInterval(fetchNotifications, 30000);
  return () => clearInterval(interval);
}, []);
```

---

## 🎯 Future Enhancements

1. **WebSocket Support** - Real-time notifications using Django Channels
2. **Slack Integration** - Send notifications to Slack channels
3. **SMS Notifications** - Via Twilio or similar service
4. **Push Notifications** - Mobile app notifications
5. **Notification Templates** - Rich HTML email templates
6. **Notification Batching** - Digest emails for multiple events

---

## ✅ Summary

You now have:
- ✅ Database models for notifications
- ✅ Notification service with email support
- ✅ Integration with approval workflow
- ✅ API endpoints for frontend
- ✅ Celery configuration for async processing
- ✅ Email templates
- ✅ User preferences management

**Next steps:** Implement frontend notification UI and test the complete flow!

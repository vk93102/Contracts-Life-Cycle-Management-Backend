import uuid
from django.db import models


class ClauseLibraryItem(models.Model):
    """Tenant-scoped clause library for the Review feature.

    This is separate from `contracts.Clause` to avoid polluting the drafting clause catalog.
    Embeddings are cached for faster match scoring.
    """

    RISK_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    key = models.CharField(max_length=200)
    category = models.CharField(max_length=120, db_index=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    default_risk = models.CharField(max_length=10, choices=RISK_CHOICES, default='medium')
    embedding = models.JSONField(default=list, blank=True)
    created_by = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_clause_library'
        unique_together = [('tenant_id', 'key')]
        indexes = [
            models.Index(fields=['tenant_id', 'category']),
        ]

    def __str__(self):
        return f"{self.category}: {self.title}"


class ReviewContract(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploaded'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tenant_id = models.UUIDField(db_index=True)
    created_by = models.UUIDField(db_index=True)

    title = models.CharField(max_length=255, blank=True, default='')
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=24, blank=True, default='')
    size_bytes = models.IntegerField(default=0)

    r2_key = models.CharField(max_length=1024, db_index=True)

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='uploaded')
    error_message = models.TextField(blank=True, default='')

    extracted_text = models.TextField(blank=True, default='')
    embedding = models.JSONField(null=True, blank=True)  # list[float]

    analysis = models.JSONField(default=dict, blank=True)
    review_text = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_contracts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title or self.original_filename} ({self.id})"

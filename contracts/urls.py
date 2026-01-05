"""
URL configuration for contracts app
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .generation_views import (
    ContractTemplateViewSet,
    ClauseViewSet,
    ContractViewSet,
    GenerationJobViewSet,
)
from .workflow_views import (
    WorkflowDefinitionViewSet,
    WorkflowInstanceViewSet,
    ApprovalViewSet,
    SLARuleViewSet,
    SLABreachViewSet,
    AuditLogViewSet,
    UserRoleViewSet,
    NotificationViewSet,
)
from .ai_views import (
    SearchViewSet,
    AIAnalysisViewSet,
    DocumentProcessingViewSet,
    AsyncContractGenerationViewSet,
)

router = DefaultRouter()
router.register(r'contract-templates', ContractTemplateViewSet, basename='contract-template')
router.register(r'clauses', ClauseViewSet, basename='clause')
router.register(r'contracts', ContractViewSet, basename='contract')
router.register(r'generation-jobs', GenerationJobViewSet, basename='generation-job')

# Workflow management endpoints
router.register(r'workflows/config', WorkflowDefinitionViewSet, basename='workflow-definition')
router.register(r'workflows/instances', WorkflowInstanceViewSet, basename='workflow-instance')
router.register(r'approvals', ApprovalViewSet, basename='approval')

# Admin endpoints
router.register(r'admin/sla-rules', SLARuleViewSet, basename='sla-rule')
router.register(r'admin/sla-breaches', SLABreachViewSet, basename='sla-breach')
router.register(r'admin/users/roles', UserRoleViewSet, basename='user-role')

# Audit and notifications
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
router.register(r'notifications', NotificationViewSet, basename='notification')

# AI-Powered Features
router.register(r'search', SearchViewSet, basename='search')
router.register(r'analysis', AIAnalysisViewSet, basename='ai-analysis')
router.register(r'documents', DocumentProcessingViewSet, basename='document-processing')
router.register(r'generation', AsyncContractGenerationViewSet, basename='async-generation')

urlpatterns = [
    path('', include(router.urls)),
    path('health/', include('contracts.urls_health')),
]

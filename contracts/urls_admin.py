"""
Admin API URLs for Contract Management Dashboard
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .admin_views import (
    AdminContractViewSet,
    AdminTemplateViewSet,
    AdminClauseViewSet,
    ApprovalActionView,
    ContractHistoryView,
)

router = DefaultRouter()
router.register(r'contracts', AdminContractViewSet, basename='admin-contract')
router.register(r'templates', AdminTemplateViewSet, basename='admin-template')
router.register(r'clauses', AdminClauseViewSet, basename='admin-clause')

urlpatterns = [
    # Router endpoints
    path('', include(router.urls)),
    
    # Custom approval actions
    path('contracts/<uuid:contract_id>/approve/', ApprovalActionView.as_view(), name='contract-approve'),
    path('contracts/<uuid:contract_id>/history/', ContractHistoryView.as_view(), name='contract-history'),
]

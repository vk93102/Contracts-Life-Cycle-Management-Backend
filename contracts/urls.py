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

router = DefaultRouter()
router.register(r'contract-templates', ContractTemplateViewSet, basename='contract-template')
router.register(r'clauses', ClauseViewSet, basename='clause')
router.register(r'contracts', ContractViewSet, basename='contract')
router.register(r'generation-jobs', GenerationJobViewSet, basename='generation-job')

urlpatterns = [
    path('', include(router.urls)),
]

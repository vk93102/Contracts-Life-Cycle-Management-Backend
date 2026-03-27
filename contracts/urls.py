"""
URL configuration for contracts app - Consolidated
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .template_views import (
    TemplateTypesView,
    TemplateTypeSummaryView,
    TemplateTypeDetailView,
    TemplateFileView,
    CreateTemplateFromTypeView,
    ValidateTemplateDataView,
    UserTemplatesView,
    DeleteTemplateView
)
from .template_file_views import (
    TemplateFileContentView,
    TemplateFileSchemaView,
    TemplateFilesView,
    TemplateMyFilesView,
    TemplateFileSignatureFieldsConfigView,
    TemplateFileDragSignaturePositionsView,
    TemplateFileDeleteView,
)
from .pdf_views import (
    ContractPDFDownloadView,
    ContractBatchPDFGenerationView,
    PDFGenerationStatusView
)

router = DefaultRouter()
router.register(r'contract-templates', views.ContractTemplateViewSet, basename='contract-template')
router.register(r'clauses', views.ClauseViewSet, basename='clause')
router.register(r'contracts', views.ContractViewSet, basename='contract')
router.register(r'generation-jobs', views.GenerationJobViewSet, basename='generation-job')

urlpatterns = [
    # ========== TEMPLATE MANAGEMENT ENDPOINTS ==========
    path('templates/types/', TemplateTypesView.as_view(), name='template-types'),
    path('templates/types/<str:template_type>/', TemplateTypeDetailView.as_view(), name='template-type-detail'),
    path('templates/files/', TemplateFilesView.as_view(), name='template-files-list'),
    path('templates/files/mine/', TemplateMyFilesView.as_view(), name='template-files-mine'),
    path('templates/files/schema/<str:filename>/', TemplateFileSchemaView.as_view(), name='template-files-schema'),
    path('templates/files/content/<str:filename>/', TemplateFileContentView.as_view(), name='template-files-content'),
    path('templates/files/signature-fields-config/<str:filename>/', TemplateFileSignatureFieldsConfigView.as_view(), name='template-files-signature-fields-config'),
    path('templates/files/drag-signature-positions/<str:filename>/', TemplateFileDragSignaturePositionsView.as_view(), name='template-files-drag-signature-positions'),
    path('templates/files/delete/<str:filename>/', TemplateFileDeleteView.as_view(), name='template-files-delete'),
    path('templates/summary/', TemplateTypeSummaryView.as_view(), name='template-summary'),
    path('templates/create-from-type/', CreateTemplateFromTypeView.as_view(), name='create-template-from-type'),
    path('templates/validate/', ValidateTemplateDataView.as_view(), name='validate-template-data'),
    
    # User template management (authenticated)
    path('templates/user/', UserTemplatesView.as_view(), name='user-templates'),
    path('templates/<uuid:template_id>/', DeleteTemplateView.as_view(), name='delete-template'),
    
    # ========== PDF GENERATION ENDPOINTS ==========
    path('<uuid:template_id>/download-pdf/', ContractPDFDownloadView.as_view(), name='contract-pdf-download'),
    path('batch-generate-pdf/', ContractBatchPDFGenerationView.as_view(), name='batch-pdf-generation'),
    path('pdf-generation-status/', PDFGenerationStatusView.as_view(), name='pdf-generation-status'),
    
    # ========== CLOUDFLARE R2 UPLOAD ENDPOINTS ==========
    path('upload-document/', views.upload_document, name='upload-document'),
    path('upload-contract-document/', views.upload_contract_document, name='upload-contract-document'),
    path('document-download-url/', views.get_document_download_url, name='document-download-url'),
    path('<uuid:contract_id>/download-url/', views.get_contract_download_url, name='contract-download-url'),
    
    # ========== INHOUSE E-SIGNATURE ENDPOINTS ==========
    # Keep in-house e-signature routing in its own module so it can be mounted
    # both under /api/v1/ (via this file) and under /api/ as a compatibility alias.
    path('', include('contracts.inhouse_urls')),

    # ========== HEALTH CHECK ENDPOINT ==========
    path('health/', views.HealthCheckView.as_view(), name='health-check'),

    # Keep any existing template_type-based route last to avoid swallowing the above
    path('templates/files/<str:template_type>/', TemplateFileView.as_view(), name='template-file'),

    # Router endpoints last. This avoids shadowing explicit paths like `contracts/upload/`.
    path('', include(router.urls)),
]


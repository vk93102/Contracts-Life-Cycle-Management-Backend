"""
URL configuration for contracts app - Consolidated
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import firma_views
from . import inhouse_esign_views
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
    
    # ========== SIGNNOW E-SIGNATURE ENDPOINTS ==========
    path('contracts/upload/', views.upload_contract, name='upload_contract'),
    path('esign/send/', views.send_for_signature, name='send_for_signature'),
    path('esign/signing-url/<str:contract_id>/', views.get_signing_url, name='get_signing_url'),
    path('esign/status/<str:contract_id>/', views.check_status, name='check_status'),
    path('esign/executed/<str:contract_id>/', views.get_executed_document, name='get_executed_document'),

    # ========== INHOUSE E-SIGNATURE ENDPOINTS ==========
    path('inhouse/esign/start/', inhouse_esign_views.inhouse_start, name='inhouse_esign_start'),
    path('inhouse/esign/status/<uuid:contract_id>/', inhouse_esign_views.inhouse_status, name='inhouse_esign_status'),
    path('inhouse/esign/executed/<uuid:contract_id>/', inhouse_esign_views.inhouse_download_executed, name='inhouse_esign_executed'),
    path('inhouse/esign/certificate/<uuid:contract_id>/', inhouse_esign_views.inhouse_download_certificate, name='inhouse_esign_certificate'),
    # signer-facing endpoints (no auth; token is the secret)
    path('inhouse/esign/session/<uuid:token>/', inhouse_esign_views.inhouse_session, name='inhouse_esign_session'),
    path('inhouse/esign/pdf/<uuid:token>/', inhouse_esign_views.inhouse_pdf, name='inhouse_esign_pdf'),
    path('inhouse/esign/sign/<uuid:token>/', inhouse_esign_views.inhouse_sign, name='inhouse_esign_sign'),

    # ========== FIRMA E-SIGNATURE ENDPOINTS ==========
    path('firma/sign/', firma_views.firma_sign, name='firma_sign'),
    path('firma/contracts/upload/', firma_views.firma_upload_contract, name='firma_upload_contract'),
    path('firma/esign/send/', firma_views.firma_send_for_signature, name='firma_send_for_signature'),
    path('firma/esign/invite-all/', firma_views.firma_invite_all, name='firma_invite_all'),
    path('firma/esign/signing-url/<str:contract_id>/', firma_views.firma_get_signing_url, name='firma_get_signing_url'),
    path('firma/esign/requests/', firma_views.firma_list_signing_requests, name='firma_list_signing_requests'),
    path('firma/esign/requests/<uuid:record_id>/', firma_views.firma_delete_signing_request, name='firma_delete_signing_request'),
    path('firma/esign/status/<str:contract_id>/', firma_views.firma_check_status, name='firma_check_status'),
    path('firma/esign/executed/<str:contract_id>/', firma_views.firma_get_executed_document, name='firma_get_executed_document'),
    path('firma/esign/certificate/<str:contract_id>/', firma_views.firma_get_certificate_document, name='firma_get_certificate_document'),
    path('firma/esign/details/<str:contract_id>/', firma_views.firma_get_signing_request_details, name='firma_get_signing_request_details'),
    path('firma/esign/reminders/<str:contract_id>/', firma_views.firma_get_signing_request_reminders, name='firma_get_signing_request_reminders'),
    path('firma/esign/activity/<str:contract_id>/', firma_views.firma_get_activity_log, name='firma_get_activity_log'),
    path('firma/esign/resend/<str:contract_id>/', firma_views.firma_resend_invites, name='firma_resend_invites'),

    path('firma/webhooks/', firma_views.firma_webhooks, name='firma_webhooks'),
    path('firma/webhooks/<str:webhook_id>/', firma_views.firma_webhook_detail, name='firma_webhook_detail'),
    path('firma/webhooks/secret-status/', firma_views.firma_webhook_secret_status, name='firma_webhook_secret_status'),
    # Vendor callback (no auth) + authenticated realtime stream for UI.
    path('firma/webhooks/receive/', firma_views.firma_webhook_receive, name='firma_webhook_receive'),
    path('firma/webhooks/stream/<str:contract_id>/', firma_views.firma_webhook_stream, name='firma_webhook_stream'),

    path('firma/jwt/template/generate/', firma_views.firma_generate_template_token, name='firma_generate_template_token'),
    path('firma/jwt/template/revoke/', firma_views.firma_revoke_template_token, name='firma_revoke_template_token'),
    path('firma/jwt/signing-request/generate/', firma_views.firma_jwt_generate_signing_request, name='firma_jwt_generate_signing_request'),
    path('firma/jwt/signing-request/revoke/', firma_views.firma_jwt_revoke_signing_request, name='firma_jwt_revoke_signing_request'),
    path('firma/debug/config/', firma_views.firma_debug_config, name='firma_debug_config'),
    path('firma/debug/connectivity/', firma_views.firma_debug_connectivity, name='firma_debug_connectivity'),
    
    # ========== HEALTH CHECK ENDPOINT ==========
    path('health/', views.HealthCheckView.as_view(), name='health-check'),

    # Keep any existing template_type-based route last to avoid swallowing the above
    path('templates/files/<str:template_type>/', TemplateFileView.as_view(), name='template-file'),

    # Router endpoints last. This avoids shadowing explicit paths like `contracts/upload/`.
    path('', include(router.urls)),
]


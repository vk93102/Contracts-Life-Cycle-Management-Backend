from django.urls import path

from . import inhouse_esign_views

urlpatterns = [
    path("inhouse/esign/start/", inhouse_esign_views.inhouse_start, name="inhouse_esign_start"),
    path("inhouse/esign/requests/", inhouse_esign_views.inhouse_requests, name="inhouse_esign_requests"),
    path("inhouse/esign/status/<uuid:contract_id>/", inhouse_esign_views.inhouse_status, name="inhouse_esign_status"),
    path("inhouse/esign/audit/<uuid:contract_id>/", inhouse_esign_views.inhouse_audit, name="inhouse_esign_audit"),
    path(
        "inhouse/esign/executed/<uuid:contract_id>/",
        inhouse_esign_views.inhouse_download_executed,
        name="inhouse_esign_executed",
    ),
    path(
        "inhouse/esign/certificate/<uuid:contract_id>/",
        inhouse_esign_views.inhouse_download_certificate,
        name="inhouse_esign_certificate",
    ),
    # signer-facing endpoints (no auth; token is the secret)
    path("inhouse/esign/session/<uuid:token>/", inhouse_esign_views.inhouse_session, name="inhouse_esign_session"),
    path("inhouse/esign/pdf/<uuid:token>/", inhouse_esign_views.inhouse_pdf, name="inhouse_esign_pdf"),
    path("inhouse/esign/sign/<uuid:token>/", inhouse_esign_views.inhouse_sign, name="inhouse_esign_sign"),
]

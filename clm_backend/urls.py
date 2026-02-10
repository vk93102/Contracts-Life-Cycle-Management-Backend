"""
URL configuration for clm_backend project.
"""
from django.contrib import admin
from django.urls import path, include

from clm_backend.metrics import metrics_view

from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('metrics', metrics_view),
    path('api/auth/', include('authentication.urls')),
    path('api/v1/admin/', include('authentication.admin_urls')),
    path('api/', include('notifications.urls')),
    path('api/v1/', include('repository.private_upload_urls')),
    path('api/v1/', include('contracts.urls')),
    path('api/v1/', include('ai.urls')),
    path('api/v1/', include('reviews.urls')),
    path('api/v1/', include('calendar_events.urls')),
    path('api/v1/', include('workflows.urls')),
    path('api/v1/', include('approvals.urls')),
]

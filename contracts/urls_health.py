"""
Health check URLs
"""
from django.urls import path
from .health_views import HealthCheckView

urlpatterns = [
    path('', HealthCheckView.as_view(), name='health_check'),
]

from django.contrib import admin
from django.urls import path, include

from clm_backend.metrics import metrics_view
from clm_backend.admin_site import admin_site

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    path('admin/', admin_site.urls),
    path('metrics', metrics_view),

    # OpenAPI/Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='openapi-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='openapi-schema'), name='swagger-ui'),

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
    path('api/v1/', include('authentication.dashboard_urls')),

    # Search endpoints (used by frontend ApiClient under /api/search/)
    path('api/search/', include('search.urls')),
]

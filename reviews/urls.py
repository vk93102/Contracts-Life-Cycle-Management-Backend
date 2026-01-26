from rest_framework.routers import DefaultRouter
from django.urls import include, path

from .views import ReviewContractViewSet
from .views_clause_library import ClauseLibraryViewSet

router = DefaultRouter()
router.register(r'review-contracts', ReviewContractViewSet, basename='review-contract')
router.register(r'clause-library', ClauseLibraryViewSet, basename='clause-library')

urlpatterns = [
    path('', include(router.urls)),
]

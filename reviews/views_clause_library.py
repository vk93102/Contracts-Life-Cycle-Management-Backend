from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClauseLibraryItem
from .serializers_clause_library import ClauseLibraryItemSerializer
from .services import ensure_clause_library_seeded


class ClauseLibraryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ClauseLibraryItemSerializer

    def get_queryset(self):
        tenant_id = getattr(self.request.user, 'tenant_id', None)
        qs = ClauseLibraryItem.objects.none()
        if tenant_id:
            qs = ClauseLibraryItem.objects.filter(tenant_id=tenant_id)

        q = (self.request.query_params.get('q') or '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(title__icontains=q) | Q(category__icontains=q) | Q(content__icontains=q))

        category = (self.request.query_params.get('category') or '').strip()
        if category:
            qs = qs.filter(category__iexact=category)

        return qs.order_by('category', 'title')

    def list(self, request, *args, **kwargs):
        # Ensure tenant has a seeded library (created on-demand).
        tenant_id = getattr(request.user, 'tenant_id', None)
        user_id = getattr(request.user, 'user_id', None)
        if tenant_id:
            ensure_clause_library_seeded(str(tenant_id), str(user_id) if user_id else None)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Read-only'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

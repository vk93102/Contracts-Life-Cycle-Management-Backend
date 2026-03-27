from __future__ import annotations

from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            connection.ensure_connection()
            db_status = "healthy"
        except Exception:
            db_status = "unhealthy"

        return Response({"status": "ok", "database": db_status, "service": "CLM Backend API"})

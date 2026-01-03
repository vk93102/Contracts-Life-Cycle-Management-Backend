"""
Health check endpoint
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import connection


class HealthCheckView(APIView):
    """
    GET /api/v1/health/ - Health check endpoint
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """
        Basic health check
        """
        try:
            # Check database connection
            connection.ensure_connection()
            db_status = 'healthy'
        except Exception:
            db_status = 'unhealthy'
        
        return Response({
            'status': 'ok',
            'database': db_status,
            'service': 'CLM Backend API'
        })

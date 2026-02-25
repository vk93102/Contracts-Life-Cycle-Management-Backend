from __future__ import annotations

from django.db.models import Q
from django.db.models import Count, Sum, Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .models import User
from .permissions import IsAdminUser, IsSuperAdminUser

from contracts.models import (
    Contract,
    ContractTemplate,
    Clause,
    FirmaSignatureContract,
    FirmaSigner,
    FirmaSigningAuditLog,
    SigningAuditLog,
    WorkflowLog,
)
from approvals.models import ApprovalModel
from audit_logs.models import AuditLogModel
from ai.models import DraftGenerationTask
from calendar_events.models import CalendarEvent
from reviews.models import ReviewContract


def _current_user_payload(user) -> dict:
    user_id = getattr(user, 'user_id', None) or getattr(user, 'pk', None) or ''
    email = getattr(user, 'email', None)
    tenant_id = getattr(user, 'tenant_id', None)
    is_admin = bool(
        getattr(user, 'is_admin', False)
        or getattr(user, 'is_staff', False)
        or getattr(user, 'is_superuser', False)
    )
    return {
        'user_id': str(user_id),
        'email': email,
        'tenant_id': str(tenant_id) if tenant_id is not None else None,
        'is_admin': is_admin,
    }


class AdminMeView(APIView):
    """GET /api/v1/admin/me/ - admin session info"""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        return Response(_current_user_payload(request.user), status=status.HTTP_200_OK)


class AdminUsersView(APIView):
    """Admin user management.

    GET /api/v1/admin/users/?q=...  -> list users (tenant-scoped)
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        is_superadmin = bool(
            getattr(request.user, 'is_superadmin', False)
            or getattr(request.user, 'is_superuser', False)
        )
        all_tenants = (request.query_params.get('all_tenants') or '').strip() in {'1', 'true', 'yes'}

        q = (request.query_params.get('q') or '').strip()
        qs = User.objects.all().order_by('email') if (is_superadmin and all_tenants) else User.objects.filter(tenant_id=tenant_id).order_by('email')
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        results = [
            {
                'user_id': str(u.user_id),
                'email': u.email,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'tenant_id': str(u.tenant_id),
                'is_active': u.is_active,
                'is_admin': bool(u.is_staff or u.is_superuser),
                'date_joined': u.date_joined,
                'last_login': u.last_login,
            }
            for u in qs[:500]
        ]

        return Response({'count': len(results), 'results': results}, status=status.HTTP_200_OK)


class AdminPromoteUserView(APIView):
    """POST /api/v1/admin/users/promote/ - promote existing user to admin."""

    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def post(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = (request.data.get('user_id') or '').strip()
        email = (request.data.get('email') or '').strip().lower()

        if not user_id and not email:
            return Response({'error': 'Provide user_id or email'}, status=status.HTTP_400_BAD_REQUEST)

        is_superadmin = bool(
            getattr(request.user, 'is_superadmin', False)
            or getattr(request.user, 'is_superuser', False)
        )
        all_tenants = (request.query_params.get('all_tenants') or '').strip() in {'1', 'true', 'yes'}

        qs = User.objects.all() if (is_superadmin and all_tenants) else User.objects.filter(tenant_id=tenant_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        else:
            qs = qs.filter(email=email)

        user = qs.first()
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.is_staff or user.is_superuser:
            return Response({'message': 'User is already an admin', 'user_id': str(user.user_id)}, status=status.HTTP_200_OK)

        user.is_staff = True
        user.save(update_fields=['is_staff'])

        return Response({
            'message': 'User promoted to admin. They must re-login to get updated admin access in their token.',
            'user': {
                'user_id': str(user.user_id),
                'email': user.email,
                'tenant_id': str(user.tenant_id),
                'is_admin': True,
            }
        }, status=status.HTTP_200_OK)


class AdminDemoteUserView(APIView):
    """POST /api/v1/admin/users/demote/ - remove admin rights (is_staff)."""

    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def post(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = (request.data.get('user_id') or '').strip()
        email = (request.data.get('email') or '').strip().lower()

        if not user_id and not email:
            return Response({'error': 'Provide user_id or email'}, status=status.HTTP_400_BAD_REQUEST)

        is_superadmin = bool(
            getattr(request.user, 'is_superadmin', False)
            or getattr(request.user, 'is_superuser', False)
        )
        all_tenants = (request.query_params.get('all_tenants') or '').strip() in {'1', 'true', 'yes'}

        qs = User.objects.all() if (is_superadmin and all_tenants) else User.objects.filter(tenant_id=tenant_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        else:
            qs = qs.filter(email=email)

        user = qs.first()
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        # Avoid removing superuser via this endpoint.
        if user.is_superuser:
            return Response({'error': 'Cannot demote a superuser via API'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_staff:
            return Response({'message': 'User is not an admin', 'user_id': str(user.user_id)}, status=status.HTTP_200_OK)

        user.is_staff = False
        user.save(update_fields=['is_staff'])

        return Response({
            'message': 'User demoted. They must re-login to lose admin access in their token.',
            'user': {
                'user_id': str(user.user_id),
                'email': user.email,
                'tenant_id': str(user.tenant_id),
                'is_admin': False,
            }
        }, status=status.HTTP_200_OK)


class AdminAnalyticsView(APIView):
    """GET /api/v1/admin/analytics/ - high-level analytics for admin dashboard."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        users_qs = User.objects.filter(tenant_id=tenant_id)
        templates_qs = ContractTemplate.objects.filter(tenant_id=tenant_id)
        clauses_qs = Clause.objects.filter(tenant_id=tenant_id)
        contracts_qs = Contract.objects.filter(tenant_id=tenant_id)
        approvals_qs = ApprovalModel.objects.filter(tenant_id=tenant_id)
        firma_sc_qs = FirmaSignatureContract.objects.filter(contract__tenant_id=tenant_id)
        firma_signers_qs = FirmaSigner.objects.filter(firma_signature_contract__contract__tenant_id=tenant_id)

        def by_status(qs, field: str = 'status'):
            rows = qs.values(field).annotate(count=Count('id')).order_by()
            return {str(r[field] or 'unknown'): int(r['count']) for r in rows}

        def last_month_starts(months: int = 6):
            """Return month-start datetimes for the last N months (inclusive of current month)."""
            if months < 1:
                months = 1
            base = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            starts = []
            for i in range(months - 1, -1, -1):
                y = base.year
                m = base.month - i
                while m <= 0:
                    y -= 1
                    m += 12
                while m > 12:
                    y += 1
                    m -= 12
                starts.append(base.replace(year=y, month=m))
            return starts

        def last_day_starts(days: int = 7):
            """Return day-start datetimes for the last N days (inclusive of today)."""
            if days < 1:
                days = 1
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return [base - timedelta(days=i) for i in range(days - 1, -1, -1)]

        month_starts = last_month_starts(6)
        trend_start = month_starts[0]

        def month_bucket_map(qs, date_field: str, start_dt):
            rows = (
                qs.filter(**{f"{date_field}__gte": start_dt})
                .exclude(**{date_field: None})
                .annotate(month=TruncMonth(date_field))
                .values('month')
                .annotate(count=Count('id'))
                .order_by()
            )
            return {r['month'].date().isoformat(): int(r['count']) for r in rows if r.get('month')}

        def day_bucket_map(qs, date_field: str, start_dt):
            rows = (
                qs.filter(**{f"{date_field}__gte": start_dt})
                .exclude(**{date_field: None})
                .annotate(day=TruncDay(date_field))
                .values('day')
                .annotate(count=Count('id'))
                .order_by()
            )
            return {r['day'].date().isoformat(): int(r['count']) for r in rows if r.get('day')}

        contracts_by_month = month_bucket_map(contracts_qs, 'created_at', trend_start)
        templates_by_month = month_bucket_map(templates_qs, 'created_at', trend_start)
        firma_sent_by_month = month_bucket_map(firma_sc_qs, 'sent_at', trend_start)
        firma_completed_by_month = month_bucket_map(firma_sc_qs, 'completed_at', trend_start)

        # AI usage trends (monthly) - based on first-class models
        ai_reviews_by_month = month_bucket_map(ReviewContract.objects.filter(tenant_id=tenant_id), 'created_at', trend_start)
        ai_generations_by_month = month_bucket_map(DraftGenerationTask.objects.filter(tenant_id=tenant_id), 'created_at', trend_start)

        trends = []
        for d in month_starts:
            key = d.date().isoformat()
            trends.append({
                'month_start': d.date().isoformat(),
                'label': d.strftime('%b %Y'),
                'contracts_created': contracts_by_month.get(key, 0),
                'templates_created': templates_by_month.get(key, 0),
                'firma_sent': firma_sent_by_month.get(key, 0),
                'firma_completed': firma_completed_by_month.get(key, 0),
            })

        ai_reviews_trend_6m = []
        ai_generations_trend_6m = []
        for d in month_starts:
            key = d.date().isoformat()
            ai_reviews_trend_6m.append({
                'month_start': d.date().isoformat(),
                'label': d.strftime('%b %Y'),
                'count': ai_reviews_by_month.get(key, 0),
            })
            ai_generations_trend_6m.append({
                'month_start': d.date().isoformat(),
                'label': d.strftime('%b %Y'),
                'count': ai_generations_by_month.get(key, 0),
            })

        # 12-month trends for "Year" filter
        month_starts_12 = last_month_starts(12)
        trend_start_12 = month_starts_12[0]
        contracts_by_month_12 = month_bucket_map(contracts_qs, 'created_at', trend_start_12)
        templates_by_month_12 = month_bucket_map(templates_qs, 'created_at', trend_start_12)
        firma_sent_by_month_12 = month_bucket_map(firma_sc_qs, 'sent_at', trend_start_12)
        firma_completed_by_month_12 = month_bucket_map(firma_sc_qs, 'completed_at', trend_start_12)

        trends_12 = []
        for d in month_starts_12:
            key = d.date().isoformat()
            trends_12.append({
                'month_start': d.date().isoformat(),
                'label': d.strftime('%b %Y'),
                'contracts_created': contracts_by_month_12.get(key, 0),
                'templates_created': templates_by_month_12.get(key, 0),
                'firma_sent': firma_sent_by_month_12.get(key, 0),
                'firma_completed': firma_completed_by_month_12.get(key, 0),
            })

        # 7-day trends for "Week" filter
        day_starts = last_day_starts(7)
        day_trend_start = day_starts[0]
        contracts_by_day = day_bucket_map(contracts_qs, 'created_at', day_trend_start)
        templates_by_day = day_bucket_map(templates_qs, 'created_at', day_trend_start)
        firma_sent_by_day = day_bucket_map(firma_sc_qs, 'sent_at', day_trend_start)
        firma_completed_by_day = day_bucket_map(firma_sc_qs, 'completed_at', day_trend_start)
        audit_by_day = day_bucket_map(AuditLogModel.objects.filter(tenant_id=tenant_id), 'created_at', day_trend_start)

        trends_7d = []
        for d in day_starts:
            key = d.date().isoformat()
            trends_7d.append({
                'day_start': key,
                'label': d.strftime('%a'),
                'contracts_created': contracts_by_day.get(key, 0),
                'templates_created': templates_by_day.get(key, 0),
                'firma_sent': firma_sent_by_day.get(key, 0),
                'firma_completed': firma_completed_by_day.get(key, 0),
                'audit_logs': audit_by_day.get(key, 0),
            })

        contract_value_agg = contracts_qs.aggregate(total_value=Sum('value'), avg_value=Avg('value'))
        total_value = contract_value_agg.get('total_value')
        avg_value = contract_value_agg.get('avg_value')

        expiring_7d = contracts_qs.filter(end_date__isnull=False, end_date__lte=(now.date() + timedelta(days=7)), end_date__gte=now.date()).count()
        expiring_30d = contracts_qs.filter(end_date__isnull=False, end_date__lte=(now.date() + timedelta(days=30)), end_date__gte=now.date()).count()

        contracts_by_type_rows = (
            contracts_qs.values('contract_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        contracts_by_type = [
            {'contract_type': (r['contract_type'] or 'unknown'), 'count': int(r['count'])}
            for r in contracts_by_type_rows[:12]
        ]

        top_templates_rows = (
            templates_qs.annotate(contracts_count=Count('contracts'))
            .order_by('-contracts_count', '-created_at')
            .values('id', 'name', 'contract_type', 'status', 'contracts_count')
        )
        top_templates = [
            {
                'template_id': str(r['id']),
                'name': r.get('name'),
                'contract_type': r.get('contract_type'),
                'status': r.get('status'),
                'contracts_count': int(r.get('contracts_count') or 0),
            }
            for r in top_templates_rows[:8]
        ]

        firma_completion_time = firma_sc_qs.filter(sent_at__isnull=False, completed_at__isnull=False).annotate(
            duration=ExpressionWrapper(F('completed_at') - F('sent_at'), output_field=DurationField())
        ).aggregate(avg_duration=Avg('duration'))
        avg_duration = firma_completion_time.get('avg_duration')
        avg_completion_seconds = int(avg_duration.total_seconds()) if avg_duration else None

        payload = {
            'tenant_id': str(tenant_id),
            'generated_at': now,
            'trends_last_6_months': trends,
            'trends_last_12_months': trends_12,
            'trends_last_7_days': trends_7d,
            'users': {
                'total': users_qs.count(),
                'active': users_qs.filter(is_active=True).count(),
                'admins': users_qs.filter(is_staff=True).count() + users_qs.filter(is_superuser=True).exclude(is_staff=True).count(),
                'superadmins': users_qs.filter(is_superuser=True).count(),
                'joined_last_7d': users_qs.filter(date_joined__gte=last_7d).count(),
                'joined_last_30d': users_qs.filter(date_joined__gte=last_30d).count(),
            },
            'templates': {
                'total': templates_qs.count(),
                'by_status': by_status(templates_qs, 'status'),
                'created_last_7d': templates_qs.filter(created_at__gte=last_7d).count(),
                'created_last_30d': templates_qs.filter(created_at__gte=last_30d).count(),
                'top_templates': top_templates,
            },
            'ai': {
                'reviews_total': ReviewContract.objects.filter(tenant_id=tenant_id).count(),
                'generations_total': DraftGenerationTask.objects.filter(tenant_id=tenant_id).count(),
                'events_total': CalendarEvent.objects.filter(tenant_id=tenant_id).count(),
                'reviews_last_6_months': ai_reviews_trend_6m,
                'generations_last_6_months': ai_generations_trend_6m,
            },
            'clauses': {
                'total': clauses_qs.count(),
                'by_status': by_status(clauses_qs, 'status'),
                'created_last_7d': clauses_qs.filter(created_at__gte=last_7d).count(),
                'created_last_30d': clauses_qs.filter(created_at__gte=last_30d).count(),
            },
            'contracts': {
                'total': contracts_qs.count(),
                'by_status': by_status(contracts_qs, 'status'),
                'created_last_7d': contracts_qs.filter(created_at__gte=last_7d).count(),
                'created_last_30d': contracts_qs.filter(created_at__gte=last_30d).count(),
                'expiring_next_7d': expiring_7d,
                'expiring_next_30d': expiring_30d,
                'total_value': str(total_value) if total_value is not None else None,
                'avg_value': str(avg_value) if avg_value is not None else None,
                'by_contract_type': contracts_by_type,
            },
            'approvals': {
                'total': approvals_qs.count(),
                'by_status': by_status(approvals_qs, 'status'),
                'pending': approvals_qs.filter(status='pending').count(),
                'created_last_7d': approvals_qs.filter(created_at__gte=last_7d).count(),
                'created_last_30d': approvals_qs.filter(created_at__gte=last_30d).count(),
            },
            'signing_requests': {
                'firma': {
                    'total': firma_sc_qs.count(),
                    'by_status': by_status(firma_sc_qs, 'status'),
                    'by_signing_order': by_status(firma_sc_qs, 'signing_order'),
                    'sent_last_7d': firma_sc_qs.filter(sent_at__gte=last_7d).count(),
                    'completed_last_30d': firma_sc_qs.filter(completed_at__gte=last_30d).count(),
                    'avg_completion_seconds': avg_completion_seconds,
                    'signers_total': firma_signers_qs.count(),
                    'signers_by_status': by_status(firma_signers_qs, 'status'),
                }
            },
            'activity_summary': {
                'audit_logs_last_7d': AuditLogModel.objects.filter(tenant_id=tenant_id, created_at__gte=last_7d).count(),
                'workflow_logs_last_7d': WorkflowLog.objects.filter(contract__tenant_id=tenant_id, timestamp__gte=last_7d).count(),
                'signnow_events_last_7d': SigningAuditLog.objects.filter(esignature_contract__contract__tenant_id=tenant_id, created_at__gte=last_7d).count(),
                'firma_events_last_7d': FirmaSigningAuditLog.objects.filter(firma_signature_contract__contract__tenant_id=tenant_id, created_at__gte=last_7d).count(),
            },
        }

        return Response(payload, status=status.HTTP_200_OK)


class AdminFeatureUsageView(APIView):
    """GET /api/v1/admin/feature-usage/ - feature usage analytics for last 6 months."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        last_6_months = now - timedelta(days=180)

        # Feature usage by entity type over time
        feature_data = (
            AuditLogModel.objects.filter(
                tenant_id=tenant_id,
                created_at__gte=last_6_months
            )
            .annotate(month=TruncMonth('created_at'))
            .values('month', 'entity_type')
            .annotate(count=Count('id'))
            .order_by('month', 'entity_type')
        )

        # Aggregate by month
        month_features = {}
        for item in feature_data:
            month_key = item['month'].date().isoformat() if item['month'] else None
            entity_type = item['entity_type'] or 'unknown'
            if month_key:
                if month_key not in month_features:
                    month_features[month_key] = {}
                month_features[month_key][entity_type] = item['count']

        # Top features by total usage
        top_features_data = (
            AuditLogModel.objects.filter(
                tenant_id=tenant_id,
                created_at__gte=last_6_months
            )
            .values('entity_type')
            .annotate(total_usage=Count('id'), unique_users=Count('user_id', distinct=True))
            .order_by('-total_usage')
        )

        top_features = [
            {
                'feature': item['entity_type'] or 'unknown',
                'total_usage': item['total_usage'],
                'unique_users': item['unique_users'],
                'avg_per_user': round(item['total_usage'] / item['unique_users'], 2) if item['unique_users'] > 0 else 0
            }
            for item in top_features_data[:10]
        ]

        # User feature preferences (top users by feature usage)
        user_feature_data = (
            AuditLogModel.objects.filter(
                tenant_id=tenant_id,
                created_at__gte=last_6_months
            )
            .values('user_id', 'entity_type')
            .annotate(count=Count('id'))
            .order_by('-count')[:100]
        )

        users_with_activity = (
            AuditLogModel.objects.filter(
                tenant_id=tenant_id,
                created_at__gte=last_6_months
            )
            .values('user_id')
            .distinct()
            .count()
        )
        total_active_users = User.objects.filter(tenant_id=tenant_id, is_active=True).count()
        adoption_rate = round((users_with_activity / total_active_users * 100) if total_active_users > 0 else 0, 2)

        return Response({
            'month_features': month_features,
            'top_features': top_features,
            'user_feature_usage': list(user_feature_data),
            'users_with_activity': users_with_activity,
            'total_active_users': total_active_users,
            'adoption_rate': adoption_rate,
        }, status=status.HTTP_200_OK)


class AdminUserRegistrationView(APIView):
    """GET /api/v1/admin/user-registration/ - user registration trends for last 6 months."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        last_6_months = now - timedelta(days=180)

        # User registration by month
        users_by_month = (
            User.objects.filter(
                tenant_id=tenant_id,
                date_joined__gte=last_6_months
            )
            .annotate(month=TruncMonth('date_joined'))
            .values('month')
            .annotate(count=Count('user_id'), active_count=Count('user_id', filter=Q(is_active=True)))
            .order_by('month')
        )

        registration_data = []
        for item in users_by_month:
            if item['month']:
                registration_data.append({
                    'month': item['month'].date().isoformat(),
                    'label': item['month'].strftime('%b %Y'),
                    'registered': item['count'],
                    'active': item['active_count']
                })

        # Additional stats
        total_registered = User.objects.filter(tenant_id=tenant_id).count()
        total_active = User.objects.filter(tenant_id=tenant_id, is_active=True).count()
        registered_last_30d = User.objects.filter(
            tenant_id=tenant_id,
            date_joined__gte=now - timedelta(days=30)
        ).count()

        return Response({
            'registration_data': registration_data,
            'total_registered': total_registered,
            'total_active': total_active,
            'registered_last_30d': registered_last_30d,
            'active_percentage': round((total_active / total_registered * 100) if total_registered > 0 else 0, 2)
        }, status=status.HTTP_200_OK)


class AdminUserFeatureUsageView(APIView):
    """GET /api/v1/admin/user-feature-usage/ - individual user feature usage."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        last_6_months = now - timedelta(days=180)

        # Get all users and their feature usage
        users_with_activity = (
            AuditLogModel.objects.filter(
                tenant_id=tenant_id,
                created_at__gte=last_6_months
            )
            .values('user_id')
            .annotate(total_actions=Count('id'))
            .order_by('-total_actions')
        )

        user_ids = [item['user_id'] for item in users_with_activity[:20]]
        users = User.objects.filter(user_id__in=user_ids)
        user_map = {str(u.user_id): u for u in users}

        users_list = []
        for item in users_with_activity[:20]:
            user_id = item['user_id']
            user_obj = user_map.get(str(user_id))
            if user_obj:
                # Get feature breakdown for this user
                user_features = (
                    AuditLogModel.objects.filter(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        created_at__gte=last_6_months
                    )
                    .values('entity_type')
                    .annotate(count=Count('id'))
                    .order_by('-count')
                )

                users_list.append({
                    'user_id': str(user_id),
                    'email': user_obj.email,
                    'name': f"{user_obj.first_name} {user_obj.last_name}".strip() or 'Unknown',
                    'total_actions': item['total_actions'],
                    'features_used': list(user_features[:5])
                })

        # Feature usage distribution across all users
        all_user_features = (
            AuditLogModel.objects.filter(
                tenant_id=tenant_id,
                created_at__gte=last_6_months
            )
            .values('entity_type')
            .annotate(count=Count('id'), unique_users=Count('user_id', distinct=True))
            .order_by('-count')
        )

        total_active = User.objects.filter(tenant_id=tenant_id, is_active=True).count()

        feature_distribution = [
            {
                'feature': item['entity_type'] or 'unknown',
                'usage_count': item['count'],
                'user_count': item['unique_users'],
                'adoption_rate': round((item['unique_users'] / total_active * 100)) if total_active > 0 else 0
            }
            for item in all_user_features
        ]

        return Response({
            'top_users': users_list,
            'feature_distribution': feature_distribution,
            'total_users': total_active,
            'period': '6_months'
        }, status=status.HTTP_200_OK)


class AdminActivityView(APIView):
    """GET /api/v1/admin/activity/ - unified recent activity feed (tenant-scoped)."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        tenant_id = getattr(request.user, 'tenant_id', None)
        if not tenant_id:
            return Response({'error': 'tenant_id missing from token; please re-login'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            limit = int(request.query_params.get('limit', '50'))
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 200))

        audit_rows = list(
            AuditLogModel.objects.filter(tenant_id=tenant_id)
            .order_by('-created_at')[:limit]
        )
        workflow_rows = list(
            WorkflowLog.objects.filter(contract__tenant_id=tenant_id)
            .select_related('contract')
            .order_by('-timestamp')[:limit]
        )
        signnow_rows = list(
            SigningAuditLog.objects.filter(esignature_contract__contract__tenant_id=tenant_id)
            .select_related('esignature_contract', 'esignature_contract__contract')
            .order_by('-created_at')[:limit]
        )
        firma_rows = list(
            FirmaSigningAuditLog.objects.filter(firma_signature_contract__contract__tenant_id=tenant_id)
            .select_related('firma_signature_contract', 'firma_signature_contract__contract')
            .order_by('-created_at')[:limit]
        )

        items = []

        for row in audit_rows:
            items.append({
                'source': 'audit',
                'event': row.action,
                'message': f"{row.entity_type} {row.action}",
                'entity_type': row.entity_type,
                'entity_id': str(row.entity_id),
                'user_id': str(row.user_id),
                'created_at': row.created_at,
            })

        for row in workflow_rows:
            items.append({
                'source': 'workflow',
                'event': row.action,
                'message': row.comment or row.action,
                'entity_type': 'contract',
                'entity_id': str(row.contract_id),
                'contract_id': str(row.contract_id),
                'user_id': str(row.performed_by),
                'created_at': row.timestamp,
            })

        for row in signnow_rows:
            contract_id = getattr(getattr(row.esignature_contract, 'contract', None), 'id', None)
            items.append({
                'source': 'signnow',
                'event': row.event,
                'message': row.message,
                'entity_type': 'esignature_contract',
                'entity_id': str(row.esignature_contract_id),
                'contract_id': str(contract_id) if contract_id else None,
                'created_at': row.created_at,
            })

        for row in firma_rows:
            contract_id = getattr(getattr(row.firma_signature_contract, 'contract', None), 'id', None)
            items.append({
                'source': 'firma',
                'event': row.event,
                'message': row.message,
                'entity_type': 'firma_signature_contract',
                'entity_id': str(row.firma_signature_contract_id),
                'contract_id': str(contract_id) if contract_id else None,
                'created_at': row.created_at,
            })

        items.sort(key=lambda x: x.get('created_at') or timezone.now(), reverse=True)
        items = items[:limit]

        return Response({'count': len(items), 'results': items}, status=status.HTTP_200_OK)

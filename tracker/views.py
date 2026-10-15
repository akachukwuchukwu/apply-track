from django.db.models import Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters, status as http_status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Application, Company, Contact, Interview, StatusEvent
from .serializers import (
    ApplicationListSerializer, ApplicationSerializer, ChangeStatusSerializer,
    CompanySerializer, ContactSerializer, InterviewSerializer,
)


class CompanyViewSet(viewsets.ModelViewSet):
    """
    Companies aren't owned per-user — there's one shared list, same as a
    real recruiting-adjacent tool would share a company directory across
    users. Applications are what's actually scoped per-user, below.
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "company"]
    search_fields = ["role_title", "company__name"]
    ordering_fields = ["applied_date", "updated_at", "created_at"]

    def get_queryset(self):
        # The actual data-isolation boundary: every query is pre-filtered to
        # the requesting user's own applications. This is what
        # tests/test_permissions.py verifies directly — user A can never
        # see user B's applications, no matter what ID they request.
        return Application.objects.filter(owner=self.request.user).select_related("company")

    def get_serializer_class(self):
        if self.action == "list":
            return ApplicationListSerializer
        return ApplicationSerializer

    def perform_create(self, serializer):
        application = serializer.save(owner=self.request.user)
        StatusEvent.objects.create(
            application=application,
            status=application.status,
            note="Application created.",
        )

    @action(detail=True, methods=["post"], url_path="change-status")
    def change_status(self, request, pk=None):
        """
        Updates an application's status AND logs the change as a
        StatusEvent, atomically from the caller's point of view — a single
        API call, one source of truth for "what's the current status" and
        "what's the history", rather than two separate writes the client
        has to remember to make.
        """
        application = self.get_object()
        serializer = ChangeStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note", "")

        application.status = new_status
        if new_status == Application.Status.APPLIED and not application.applied_date:
            application.applied_date = timezone.now().date()
        application.save()

        StatusEvent.objects.create(application=application, status=new_status, note=note)

        return Response(ApplicationSerializer(application).data, status=http_status.HTTP_200_OK)


class ContactViewSet(viewsets.ModelViewSet):
    serializer_class = ContactSerializer

    def get_queryset(self):
        # Scoped through the parent application's owner, not a direct
        # owner field on Contact itself — same isolation guarantee, applied
        # one hop further down the relationship.
        return Contact.objects.filter(application__owner=self.request.user)


class InterviewViewSet(viewsets.ModelViewSet):
    serializer_class = InterviewSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["completed", "interview_type"]
    ordering_fields = ["scheduled_at"]

    def get_queryset(self):
        return Interview.objects.filter(application__owner=self.request.user)


class DashboardStatsView(APIView):
    """
    GET /api/dashboard/ — aggregate numbers across the requesting user's
    own applications. Deliberately a plain APIView rather than a ViewSet
    action: this isn't CRUD over a resource, it's a computed summary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        applications = Application.objects.filter(owner=request.user)
        total = applications.count()

        by_status = {
            row["status"]: row["count"]
            for row in applications.values("status").annotate(count=Count("id"))
        }

        responded_statuses = [
            Application.Status.SCREENING, Application.Status.INTERVIEWING,
            Application.Status.OFFER, Application.Status.REJECTED, Application.Status.ACCEPTED,
        ]
        applied_count = applications.exclude(status=Application.Status.WISHLIST).count()
        responded_count = applications.filter(status__in=responded_statuses).count()
        response_rate = round((responded_count / applied_count) * 100, 1) if applied_count else 0.0

        # Average days from applied_date to the first status change after
        # APPLIED, computed in Python rather than in the database query —
        # SQLite's date-diff support is limited and inconsistent across
        # backends, so this stays portable at the cost of pulling a bit
        # more data into memory. Fine at this scale; a high-volume version
        # would push this into the database with a backend-specific
        # expression instead.
        response_days = []
        for app in applications.exclude(applied_date=None).prefetch_related("status_events"):
            # Only a genuine response status counts. Excluding just APPLIED
            # would let a WISHLIST event dated on/after the apply date be
            # miscounted as the company responding; and __gte (not __gt)
            # so a same-day reply isn't silently dropped.
            first_response = (
                app.status_events.filter(
                    status__in=responded_statuses,
                    changed_at__date__gte=app.applied_date,
                )
                .order_by("changed_at")
                .first()
            )
            if first_response:
                response_days.append((first_response.changed_at.date() - app.applied_date).days)

        avg_days_to_response = round(sum(response_days) / len(response_days), 1) if response_days else None

        return Response({
            "total_applications": total,
            "by_status": by_status,
            "response_rate_percent": response_rate,
            "average_days_to_response": avg_days_to_response,
        })

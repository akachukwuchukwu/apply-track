from rest_framework import serializers

from .models import Application, Company, Contact, Interview, StatusEvent


class OwnedApplicationMixin:
    """
    Contacts and interviews point at an Application via a foreign key. The
    viewsets already hide other users' rows on *read*, but a plain
    PrimaryKeyRelatedField would still accept ANY application ID on *write*
    — letting one user attach records to another user's application. This
    closes that hole by checking ownership during validation.

    The error deliberately mirrors DRF's own "object does not exist" message,
    so a caller can't tell "doesn't exist" apart from "exists but isn't
    yours" and use that to probe for valid IDs.
    """

    def validate_application(self, application):
        request = self.context["request"]
        if application.owner_id != request.user.id:
            raise serializers.ValidationError(f'Invalid pk "{application.pk}" - object does not exist.')
        return application


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "website", "notes", "created_at"]


class StatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusEvent
        fields = ["id", "status", "note", "changed_at"]
        read_only_fields = ["changed_at"]


class ContactSerializer(OwnedApplicationMixin, serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "application", "name", "role", "email", "linkedin_url"]


class InterviewSerializer(OwnedApplicationMixin, serializers.ModelSerializer):
    class Meta:
        model = Interview
        fields = ["id", "application", "interview_type", "scheduled_at", "notes", "completed"]


class ApplicationSerializer(serializers.ModelSerializer):
    # Nested, read-only — the history/related records are managed through
    # their own endpoints (and the status-change action below), not by
    # writing directly into a parent Application payload.
    status_events = StatusEventSerializer(many=True, read_only=True)
    interviews = InterviewSerializer(many=True, read_only=True)
    contacts = ContactSerializer(many=True, read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id", "company", "company_name", "role_title", "job_url", "status",
            "applied_date", "salary_range", "notes", "created_at", "updated_at",
            "status_events", "interviews", "contacts",
        ]
        read_only_fields = ["created_at", "updated_at"]


class ApplicationListSerializer(serializers.ModelSerializer):
    """Lighter serializer for the list view — no nested history, so paging
    through many applications doesn't pull every related row for each one."""
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Application
        fields = ["id", "company", "company_name", "role_title", "status", "applied_date", "updated_at"]


class ChangeStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Application.Status.choices)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)

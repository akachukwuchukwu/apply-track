from django.contrib import admin

from .models import Application, Company, Contact, Interview, StatusEvent


class StatusEventInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ["changed_at"]


class InterviewInline(admin.TabularInline):
    model = Interview
    extra = 0


class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["role_title", "company", "status", "owner", "applied_date", "updated_at"]
    list_filter = ["status", "company"]
    search_fields = ["role_title", "company__name"]
    inlines = [StatusEventInline, InterviewInline, ContactInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Changing status here would otherwise bypass the history log that
        # the API's change-status action keeps, leaving an application whose
        # current status disagrees with its own timeline — which is exactly
        # what the dashboard's response-time statistics rely on being true.
        if not change or "status" in form.changed_data:
            StatusEvent.objects.create(
                application=obj, status=obj.status,
                note="Created in admin." if not change else "Status changed in admin.",
            )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "website"]
    search_fields = ["name"]

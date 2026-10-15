from django.conf import settings
from django.db import models
from django.utils import timezone


class Company(models.Model):
    name = models.CharField(max_length=200)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name


class Application(models.Model):
    class Status(models.TextChoices):
        WISHLIST = "WISHLIST", "Wishlist"
        APPLIED = "APPLIED", "Applied"
        SCREENING = "SCREENING", "Recruiter screen"
        INTERVIEWING = "INTERVIEWING", "Interviewing"
        OFFER = "OFFER", "Offer"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"
        ACCEPTED = "ACCEPTED", "Accepted"

    # Every application belongs to exactly one user — this is what makes
    # per-user data isolation possible, enforced in views.py's queryset
    # filtering and verified directly in tests/test_permissions.py.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="applications")
    role_title = models.CharField(max_length=200)
    job_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WISHLIST)
    applied_date = models.DateField(null=True, blank=True)
    salary_range = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.role_title} @ {self.company.name}"


class StatusEvent(models.Model):
    """
    A permanent log of every status change an application has gone through.
    Application.status always holds the *current* state; this table holds
    the history — so "how long did it take to hear back?" is answerable
    from real data instead of guessed from a single mutable field.
    """
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="status_events")
    status = models.CharField(max_length=20, choices=Application.Status.choices)
    note = models.CharField(max_length=300, blank=True)
    # default=timezone.now (not auto_now_add) deliberately — auto_now_add
    # silently ignores any explicit value passed to .create(), even on
    # purpose, which broke the seed script's attempt to backdate historical
    # events. A plain default still gives "now" for real API usage, while
    # letting code that genuinely needs to set history explicitly do so.
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["changed_at"]

    def __str__(self) -> str:
        return f"{self.application} → {self.status}"


class Contact(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    linkedin_url = models.URLField(blank=True)

    def __str__(self) -> str:
        return self.name


class Interview(models.Model):
    class Type(models.TextChoices):
        PHONE = "PHONE", "Phone screen"
        TECHNICAL = "TECHNICAL", "Technical"
        ONSITE = "ONSITE", "Onsite / virtual onsite"
        FINAL = "FINAL", "Final round"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="interviews")
    interview_type = models.CharField(max_length=20, choices=Type.choices)
    scheduled_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self) -> str:
        return f"{self.get_interview_type_display()} — {self.application}"

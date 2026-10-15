from datetime import timedelta

from django.utils import timezone

from tracker.models import Application, Company, StatusEvent


def test_string_representations(app_a, company):
    assert str(company) == "Acme Corp"
    assert str(app_a) == "Backend Engineer @ Acme Corp"


def test_status_event_timestamp_defaults_to_now_but_can_be_set_explicitly(app_a):
    # Regression test: this field used to be auto_now_add, which silently
    # ignored any explicit value and broke backdated history entirely.
    default_event = StatusEvent.objects.create(application=app_a, status="APPLIED")
    assert (timezone.now() - default_event.changed_at).total_seconds() < 5

    past = timezone.now() - timedelta(days=30)
    backdated = StatusEvent.objects.create(application=app_a, status="SCREENING", changed_at=past)
    assert backdated.changed_at == past


def test_deleting_an_application_deletes_its_history(app_a):
    StatusEvent.objects.create(application=app_a, status="APPLIED")
    app_a.delete()
    assert StatusEvent.objects.count() == 0


def test_deleting_a_user_deletes_their_applications(user_a, app_a):
    user_a.delete()
    assert Application.objects.count() == 0

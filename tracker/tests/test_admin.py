from django.contrib import admin
from django.contrib.auth.models import User

from tracker.admin import ApplicationAdmin
from tracker.models import Application


class StubForm:
    def __init__(self, changed_data):
        self.changed_data = changed_data


def test_changing_status_in_admin_logs_a_history_event(app_a):
    model_admin = ApplicationAdmin(Application, admin.site)
    app_a.status = Application.Status.OFFER
    before = app_a.status_events.count()

    model_admin.save_model(None, app_a, StubForm(["status"]), change=True)

    assert app_a.status_events.count() == before + 1
    assert app_a.status_events.last().status == "OFFER"


def test_editing_other_fields_in_admin_does_not_log_an_event(app_a):
    model_admin = ApplicationAdmin(Application, admin.site)
    app_a.notes = "Followed up by email"
    before = app_a.status_events.count()

    model_admin.save_model(None, app_a, StubForm(["notes"]), change=True)

    assert app_a.status_events.count() == before

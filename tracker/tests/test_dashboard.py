"""
The dashboard maths, checked against hand-computed numbers rather than just
"returns 200" — a stats endpoint that returns plausible-looking wrong
figures is worse than one that fails loudly.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from tracker.models import Application, StatusEvent

S = Application.Status


def make_app(owner, company, status, applied_days_ago=None, response_after_days=None):
    today = timezone.now().date()
    applied = today - timedelta(days=applied_days_ago) if applied_days_ago is not None else None
    app = Application.objects.create(
        owner=owner, company=company, role_title="Dev", status=status, applied_date=applied
    )
    if applied and response_after_days is not None:
        StatusEvent.objects.create(application=app, status=S.APPLIED,
                                   changed_at=timezone.make_aware(datetime.combine(applied, time(9, 0))))
        responded = applied + timedelta(days=response_after_days)
        StatusEvent.objects.create(application=app, status=status,
                                   changed_at=timezone.make_aware(datetime.combine(responded, time(9, 0))))
    return app


def test_empty_dashboard(client_a):
    data = client_a.get("/api/dashboard/").json()
    assert data["total_applications"] == 0
    assert data["response_rate_percent"] == 0.0
    assert data["average_days_to_response"] is None


def test_counts_by_status(client_a, user_a, company):
    make_app(user_a, company, S.APPLIED, 5)
    make_app(user_a, company, S.APPLIED, 5)
    make_app(user_a, company, S.REJECTED, 10, response_after_days=3)
    data = client_a.get("/api/dashboard/").json()
    assert data["by_status"] == {"APPLIED": 2, "REJECTED": 1}


def test_response_rate_excludes_wishlist_from_the_denominator(client_a, user_a, company):
    make_app(user_a, company, S.WISHLIST)                       # not applied yet: ignored entirely
    make_app(user_a, company, S.APPLIED, 5)                     # applied, no reply
    make_app(user_a, company, S.SCREENING, 8, response_after_days=2)  # replied
    data = client_a.get("/api/dashboard/").json()
    assert data["total_applications"] == 3
    assert data["response_rate_percent"] == 50.0                # 1 reply out of 2 applied


def test_average_days_to_response_is_computed_from_real_history(client_a, user_a, company):
    make_app(user_a, company, S.SCREENING, 20, response_after_days=2)
    make_app(user_a, company, S.REJECTED, 20, response_after_days=6)
    assert client_a.get("/api/dashboard/").json()["average_days_to_response"] == 4.0   # (2 + 6) / 2


def test_same_day_response_is_counted(client_a, user_a, company):
    make_app(user_a, company, S.SCREENING, 5, response_after_days=0)
    assert client_a.get("/api/dashboard/").json()["average_days_to_response"] == 0.0


def test_a_wishlist_event_is_not_mistaken_for_a_response(client_a, user_a, company):
    app = make_app(user_a, company, S.APPLIED, 5)
    StatusEvent.objects.create(application=app, status=S.WISHLIST,
                               changed_at=timezone.now())
    assert client_a.get("/api/dashboard/").json()["average_days_to_response"] is None

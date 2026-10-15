from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from tracker.models import Application, StatusEvent


def test_unauthenticated_requests_are_rejected():
    assert APIClient().get("/api/applications/").status_code == 401


def test_jwt_login_flow_end_to_end(db):
    User.objects.create_user(username="carol", password="carol-pass-123")
    client = APIClient()

    token_response = client.post("/api/token/", {"username": "carol", "password": "carol-pass-123"}, format="json")
    assert token_response.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.json()['access']}")
    assert client.get("/api/applications/").status_code == 200


def test_wrong_password_gets_no_token(db):
    User.objects.create_user(username="carol", password="carol-pass-123")
    response = APIClient().post("/api/token/", {"username": "carol", "password": "wrong"}, format="json")
    assert response.status_code == 401


def test_creating_an_application_assigns_owner_and_logs_first_event(client_a, user_a, company):
    response = client_a.post(
        "/api/applications/",
        {"company": company.id, "role_title": "Python Developer", "status": "APPLIED"},
        format="json",
    )
    assert response.status_code == 201

    application = Application.objects.get(id=response.json()["id"])
    assert application.owner == user_a
    assert application.status_events.count() == 1
    assert application.status_events.first().status == "APPLIED"


def test_client_cannot_choose_the_owner(client_a, user_a, user_b, company):
    # `owner` isn't an input field, so a payload naming someone else is ignored.
    response = client_a.post(
        "/api/applications/",
        {"company": company.id, "role_title": "X", "owner": user_b.id},
        format="json",
    )
    assert response.status_code == 201
    assert Application.objects.get(id=response.json()["id"]).owner == user_a


def test_list_view_uses_the_lightweight_serializer(client_a, app_a):
    row = client_a.get("/api/applications/").json()["results"][0]
    assert "status_events" not in row
    assert row["company_name"] == "Acme Corp"


def test_detail_view_includes_nested_history(client_a, app_a):
    StatusEvent.objects.create(application=app_a, status="APPLIED")
    detail = client_a.get(f"/api/applications/{app_a.id}/").json()
    assert len(detail["status_events"]) == 1


def test_filter_by_status(client_a, user_a, company, app_a):
    Application.objects.create(owner=user_a, company=company, role_title="Other", status="REJECTED")
    results = client_a.get("/api/applications/?status=REJECTED").json()
    assert results["count"] == 1
    assert results["results"][0]["status"] == "REJECTED"


def test_search_by_company_name(client_a, user_a, app_a):
    from tracker.models import Company
    other = Company.objects.create(name="Globex")
    Application.objects.create(owner=user_a, company=other, role_title="Dev")
    assert client_a.get("/api/applications/?search=Globex").json()["count"] == 1


def test_change_status_updates_application_and_logs_event(client_a, app_a):
    response = client_a.post(
        f"/api/applications/{app_a.id}/change-status/",
        {"status": "INTERVIEWING", "note": "Technical round booked"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "INTERVIEWING"

    app_a.refresh_from_db()
    assert app_a.status == "INTERVIEWING"
    last_event = app_a.status_events.last()
    assert (last_event.status, last_event.note) == ("INTERVIEWING", "Technical round booked")


def test_moving_to_applied_stamps_the_applied_date_once(client_a, user_a, company):
    wishlisted = Application.objects.create(owner=user_a, company=company, role_title="Dev")
    assert wishlisted.applied_date is None

    client_a.post(f"/api/applications/{wishlisted.id}/change-status/", {"status": "APPLIED"}, format="json")
    wishlisted.refresh_from_db()
    assert wishlisted.applied_date == timezone.now().date()


def test_change_status_rejects_an_invalid_status(client_a, app_a):
    response = client_a.post(
        f"/api/applications/{app_a.id}/change-status/", {"status": "NOT_A_STATUS"}, format="json"
    )
    assert response.status_code == 400
    app_a.refresh_from_db()
    assert app_a.status == "APPLIED"


def test_can_add_a_contact_and_interview_to_own_application(client_a, app_a):
    contact = client_a.post("/api/contacts/", {"application": app_a.id, "name": "Dana Recruiter"}, format="json")
    interview = client_a.post(
        "/api/interviews/",
        {"application": app_a.id, "interview_type": "TECHNICAL", "scheduled_at": "2026-12-01T10:00:00Z"},
        format="json",
    )
    assert contact.status_code == 201
    assert interview.status_code == 201


def test_pagination_shape(client_a, user_a, company):
    for i in range(25):
        Application.objects.create(owner=user_a, company=company, role_title=f"Role {i}")
    page = client_a.get("/api/applications/").json()
    assert page["count"] == 25
    assert len(page["results"]) == 20
    assert page["next"] is not None

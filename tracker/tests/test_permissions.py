"""
Data-isolation tests: one user must never be able to see, change, or attach
anything to another user's applications. This is the security property the
whole per-user design exists to guarantee, so it gets its own file.
"""

from tracker.models import Application, Contact, Interview


def test_user_only_sees_their_own_applications(client_a, client_b, app_a):
    assert client_a.get("/api/applications/").json()["count"] == 1
    assert client_b.get("/api/applications/").json()["count"] == 0


def test_other_users_application_returns_404_not_403(client_b, app_a):
    # 404, not 403: a 403 would confirm the ID exists, leaking information
    # about other users' data. The queryset filter makes it simply not exist
    # from B's point of view.
    assert client_b.get(f"/api/applications/{app_a.id}/").status_code == 404


def test_user_cannot_update_another_users_application(client_b, app_a):
    response = client_b.patch(f"/api/applications/{app_a.id}/", {"role_title": "Hacked"}, format="json")
    assert response.status_code == 404
    app_a.refresh_from_db()
    assert app_a.role_title == "Backend Engineer"


def test_user_cannot_delete_another_users_application(client_b, app_a):
    assert client_b.delete(f"/api/applications/{app_a.id}/").status_code == 404
    assert Application.objects.filter(id=app_a.id).exists()


def test_user_cannot_change_status_of_another_users_application(client_b, app_a):
    response = client_b.post(
        f"/api/applications/{app_a.id}/change-status/", {"status": "REJECTED"}, format="json"
    )
    assert response.status_code == 404
    app_a.refresh_from_db()
    assert app_a.status == Application.Status.APPLIED


def test_user_cannot_attach_contact_to_another_users_application(client_b, app_a):
    response = client_b.post(
        "/api/contacts/", {"application": app_a.id, "name": "Injected Contact"}, format="json"
    )
    assert response.status_code == 400
    assert not Contact.objects.filter(application=app_a).exists()


def test_user_cannot_attach_interview_to_another_users_application(client_b, app_a):
    response = client_b.post(
        "/api/interviews/",
        {"application": app_a.id, "interview_type": "PHONE", "scheduled_at": "2026-12-01T10:00:00Z"},
        format="json",
    )
    assert response.status_code == 400
    assert not Interview.objects.filter(application=app_a).exists()


def test_dashboard_only_counts_own_applications(client_a, client_b, app_a):
    assert client_a.get("/api/dashboard/").json()["total_applications"] == 1
    assert client_b.get("/api/dashboard/").json()["total_applications"] == 0

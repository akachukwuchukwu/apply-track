"""
The demo page is plain HTML served by Django; the data always comes from the
authenticated API. These tests guard the parts that are easy to break
silently.
"""

from tracker.management.commands.seed_demo_data import DEMO_PASSWORD, DEMO_USERNAME


def test_demo_page_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]
    assert "Apply Track" in response.content.decode()


def test_template_engine_left_the_javascript_alone(client):
    html = client.get("/").content.decode()
    # The page is wrapped in {% verbatim %}; if those tags leak through, or
    # the engine tried to interpret anything inside, the page would break.
    assert "verbatim" not in html
    assert "fetch(path" in html


def test_fill_demo_button_matches_the_seeded_account(client):
    # If someone changes the seeded demo credentials but not the page, the
    # "Fill demo account" button would silently stop working.
    html = client.get("/").content.decode()
    assert f"'{DEMO_USERNAME}'" in html
    assert f"'{DEMO_PASSWORD}'" in html


def test_loading_the_page_reveals_no_records(client):
    # The page is public, but every record arrives later through the API,
    # which still refuses a request with no token.
    client.get("/")
    assert client.get("/api/applications/").status_code == 401
    assert client.get("/api/dashboard/").status_code == 401

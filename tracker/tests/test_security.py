"""
Production-safety behaviour: login rate limiting, and the settings guards that
stop the app starting in an unsafe configuration.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BAD_LOGIN = {"username": "alice", "password": "wrong-password"}


# ---------------------------------------------------------------- login throttle

def test_login_is_rate_limited_after_ten_attempts(db):
    User.objects.create_user(username="alice", password="alice-pass-123")
    client = APIClient()

    for _ in range(10):
        assert client.post("/api/token/", BAD_LOGIN, format="json").status_code == 401

    blocked = client.post("/api/token/", BAD_LOGIN, format="json")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked


def test_rate_limit_applies_even_to_the_correct_password(db):
    # A throttled client shouldn't be able to slip a correct guess through.
    User.objects.create_user(username="alice", password="alice-pass-123")
    client = APIClient()
    for _ in range(10):
        client.post("/api/token/", BAD_LOGIN, format="json")

    good = client.post("/api/token/", {"username": "alice", "password": "alice-pass-123"}, format="json")
    assert good.status_code == 429


def test_each_client_address_gets_its_own_allowance(db):
    User.objects.create_user(username="alice", password="alice-pass-123")
    client = APIClient()
    for _ in range(11):
        client.post("/api/token/", BAD_LOGIN, format="json", REMOTE_ADDR="10.0.0.1")

    other = client.post("/api/token/", BAD_LOGIN, format="json", REMOTE_ADDR="10.0.0.2")
    assert other.status_code == 401        # a different address is not blocked


def test_a_forged_forwarded_header_cannot_dodge_the_limit_by_default(db):
    # NUM_PROXIES defaults to 0, so X-Forwarded-For is ignored. If it were
    # trusted, rotating the header would give an attacker unlimited attempts.
    client = APIClient()
    for i in range(10):
        client.post("/api/token/", BAD_LOGIN, format="json", HTTP_X_FORWARDED_FOR=f"1.2.3.{i}")

    response = client.post("/api/token/", BAD_LOGIN, format="json", HTTP_X_FORWARDED_FOR="9.9.9.9")
    assert response.status_code == 429


def test_behind_one_trusted_proxy_the_address_the_proxy_appended_is_used(db):
    # With NUM_PROXIES=1 the *last* entry is the one our own proxy added; any
    # earlier entries were supplied by the client and are ignored.
    rest = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    with override_settings(REST_FRAMEWORK=rest):
        client = APIClient()
        for i in range(10):
            client.post("/api/token/", BAD_LOGIN, format="json", HTTP_X_FORWARDED_FOR=f"fake-{i}, 203.0.113.7")

        same_real_client = client.post(
            "/api/token/", BAD_LOGIN, format="json", HTTP_X_FORWARDED_FOR="another-fake, 203.0.113.7"
        )
        different_client = client.post(
            "/api/token/", BAD_LOGIN, format="json", HTTP_X_FORWARDED_FOR="fake, 203.0.113.99"
        )

    assert same_real_client.status_code == 429
    assert different_client.status_code == 401


# ---------------------------------------------------------------- settings guards
# These run settings.py in a fresh process: the guard fires at import time, so
# it can't be exercised from inside an already-configured test run.

def run_settings(env: dict, expression: str = "print('ok')"):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
    clean.update(env)
    return subprocess.run(
        [sys.executable, "-c", f"import config.settings as s; {expression}"],
        cwd=PROJECT_ROOT, env=clean, capture_output=True, text=True,
    )


GOOD_KEY = "a-long-random-production-key-for-tests-1234567890"


def test_production_refuses_to_start_without_a_secret_key():
    # An empty value stands in for "unset" so a developer's local .env can't leak in.
    result = run_settings({"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": ""})
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY must be set" in result.stderr


def test_production_refuses_the_publicly_known_development_key():
    dev_key = "django-insecure-dev-only-key-replace-in-production"
    result = run_settings({"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": dev_key})
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY must be set" in result.stderr


def test_production_refuses_a_short_secret_key():
    result = run_settings({"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "too-short"})
    assert result.returncode != 0
    assert "too short" in result.stderr


def test_production_starts_with_a_real_key_and_turns_the_protections_on():
    result = run_settings(
        {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": GOOD_KEY},
        "print(s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, "
        "'whitenoise.middleware.WhiteNoiseMiddleware' in s.MIDDLEWARE)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["False", "True", "True", "True"]


def test_development_defaults_still_work_with_no_setup():
    result = run_settings(
        {"DJANGO_DEBUG": "True", "DJANGO_SECRET_KEY": ""},
        "print(s.DEBUG, s.SESSION_COOKIE_SECURE, 'whitenoise.middleware.WhiteNoiseMiddleware' in s.MIDDLEWARE)",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["True", "False", "False"]


def test_proxy_header_is_only_trusted_when_explicitly_enabled():
    base = {"DJANGO_DEBUG": "True", "DJANGO_SECRET_KEY": ""}
    off = run_settings({**base, "DJANGO_BEHIND_PROXY": "False"}, "print(hasattr(s, 'SECURE_PROXY_SSL_HEADER'))")
    on = run_settings({**base, "DJANGO_BEHIND_PROXY": "True"}, "print(s.SECURE_PROXY_SSL_HEADER)")
    assert off.stdout.strip() == "False"
    assert on.stdout.strip() == "('HTTP_X_FORWARDED_PROTO', 'https')"


def test_database_and_cache_locations_come_from_the_environment():
    result = run_settings(
        {"DJANGO_DB_PATH": "/var/lib/example/db.sqlite3", "DJANGO_CACHE_DIR": "/var/lib/example/cache"},
        "print(s.DATABASES['default']['NAME'], s.CACHES['default']['LOCATION'])",
    )
    assert result.stdout.split() == ["/var/lib/example/db.sqlite3", "/var/lib/example/cache"]


@pytest.mark.parametrize("value,expected", [("False", False), ("false", False), ("0", False), ("True", True), ("1", True)])
def test_debug_flag_parsing(value, expected):
    result = run_settings(
        {"DJANGO_DEBUG": value, "DJANGO_SECRET_KEY": GOOD_KEY}, "print(s.DEBUG)"
    )
    assert result.stdout.strip() == str(expected)


def test_https_redirect_and_hsts_are_opt_in():
    base = {"DJANGO_DEBUG": "True", "DJANGO_SECRET_KEY": ""}
    off = run_settings(base, "print(s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS)")
    on = run_settings(
        {**base, "DJANGO_SSL_REDIRECT": "True", "DJANGO_HSTS_SECONDS": "3600"},
        "print(s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS)",
    )
    assert off.stdout.split() == ["False", "0"]
    assert on.stdout.split() == ["True", "3600"]

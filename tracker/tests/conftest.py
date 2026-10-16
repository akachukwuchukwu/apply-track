import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from tracker.models import Application, Company


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="bob", password="bob-pass-123")


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Corp")


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


@pytest.fixture
def client_b(user_b):
    client = APIClient()
    client.force_authenticate(user=user_b)
    return client


@pytest.fixture
def app_a(user_a, company):
    return Application.objects.create(
        owner=user_a, company=company, role_title="Backend Engineer",
        status=Application.Status.APPLIED,
    )


@pytest.fixture(autouse=True)
def clear_rate_limit_counters():
    # The login throttle stores its counters in the (file-based) cache, which
    # outlives a single test. Clearing it keeps tests independent of each other.
    cache.clear()
    yield
    cache.clear()

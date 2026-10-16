from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from tracker.management.commands.seed_demo_data import COMPANIES, DEMO_USERNAME
from tracker.models import Application, Company, StatusEvent


def run(*args):
    out = StringIO()
    call_command("reset_demo_data", *args, stdout=out)
    return out.getvalue()


def test_it_refuses_to_run_without_explicit_confirmation(db):
    with pytest.raises(CommandError, match="--yes"):
        run()


def test_it_restores_a_demo_that_visitors_have_trashed(db):
    call_command("seed_demo_data", stdout=StringIO())
    demo = User.objects.get(username=DEMO_USERNAME)

    # what a visitor could do through the API: add junk, rename and delete shared companies
    junk_company = Company.objects.create(name="<img src=x onerror=alert(1)>")
    Application.objects.create(owner=demo, company=junk_company, role_title="spam")
    Company.objects.filter(name=COMPANIES[0]).update(name="vandalised")
    Application.objects.filter(owner=demo).first().delete()

    run("--yes")

    assert Application.objects.filter(owner=demo).count() == len(COMPANIES)
    assert not Company.objects.filter(name__icontains="onerror").exists()
    assert not Company.objects.filter(name="vandalised").exists()
    assert set(Company.objects.values_list("name", flat=True)) == set(COMPANIES)
    assert StatusEvent.objects.filter(application__owner=demo).exists()      # history was reseeded too


def test_it_never_touches_another_users_data(user_a, app_a, company):
    call_command("seed_demo_data", stdout=StringIO())

    run("--yes")

    app_a.refresh_from_db()
    assert app_a.role_title == "Backend Engineer"
    assert Company.objects.filter(pk=company.pk).exists()      # in use, so kept


def test_it_works_on_an_empty_database(db):
    run("--yes")
    assert Application.objects.filter(owner__username=DEMO_USERNAME).count() == len(COMPANIES)


def test_running_it_twice_gives_the_same_result(db):
    run("--yes")
    first = sorted(Application.objects.values_list("role_title", "status"))
    run("--yes")
    assert sorted(Application.objects.values_list("role_title", "status")) == first

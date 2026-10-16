"""
Wipes the demo account's data and reseeds it. For a public demo instance,
run nightly: a shared demo login that anyone can edit will otherwise fill up
with junk, and visitors can rename or delete the shared company list.

It only ever touches the demo user's applications (and any company left with
no applications at all). Other users' data is never deleted. Because the
company list is shared between users, don't keep a real job search on an
instance you also expose as a demo.
"""

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from tracker.management.commands.seed_demo_data import DEMO_USERNAME
from tracker.models import Application, Company


class Command(BaseCommand):
    help = "Delete the demo user's applications and reseed fresh demo data."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Confirm the deletion (required).")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("This deletes the demo user's data. Re-run with --yes to confirm.")

        demo = User.objects.filter(username=DEMO_USERNAME).first()
        removed = 0
        if demo:
            removed, _ = Application.objects.filter(owner=demo).delete()   # cascades to history, interviews, contacts

        # Companies visitors created (or that were left behind by the deletion above).
        orphans, _ = Company.objects.filter(applications__isnull=True).delete()

        call_command("seed_demo_data", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(
            f"Demo reset: removed {removed} rows of demo data and {orphans} unused companies, then reseeded."
        ))

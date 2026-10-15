"""
Seeds a demo user with synthetic job applications, for anyone cloning this
repo to explore it immediately. Not anyone's real job search — fictional
companies, randomized with a fixed seed so the demo is reproducible.

Each application gets a full, consistent status history: its current status
always matches the last event in its timeline, which is the invariant the
dashboard's response-time statistics depend on.
"""

import random
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import Application, Company, Interview, StatusEvent

COMPANIES = [
    "Northwind Analytics", "Bluepeak Systems", "Riverstone Digital",
    "Clearline Software", "Haven Robotics", "Marigold Health Tech",
    "Driftwood Labs", "Keystone Cloud", "Fernhill Data", "Anchorpoint AI",
]

ROLES = [
    "Backend Engineer", "Full-Stack Developer", "Python Developer",
    "Software Engineer", "Platform Engineer", "API Engineer",
]

# The demo page's "Fill demo account" button uses these same values;
# tests/test_page.py fails if the two ever drift apart.
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-password-123"

S = Application.Status
PROGRESSION = [S.APPLIED, S.SCREENING, S.INTERVIEWING, S.OFFER]


def build_timeline(rng: random.Random, final_status: str) -> list[str]:
    """The ordered statuses an application passed through to reach its final one."""
    if final_status == S.WISHLIST:
        return []
    if final_status == S.REJECTED:
        # Rejected after getting some distance through the process.
        reached = rng.randint(1, 3)
        return PROGRESSION[:reached] + [S.REJECTED]
    return PROGRESSION[: PROGRESSION.index(final_status) + 1]


class Command(BaseCommand):
    help = "Seeds a demo user with synthetic job-search data."

    def handle(self, *args, **options):
        rng = random.Random(42)

        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME, defaults={"email": "demo@example.com"}
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(f"Created demo user: username={DEMO_USERNAME} password={DEMO_PASSWORD}")
        else:
            self.stdout.write("Demo user already exists, reusing it.")

        if Application.objects.filter(owner=user).exists():
            self.stdout.write("Demo user already has applications, skipping seed.")
            return

        today = timezone.now().date()
        possible_outcomes = PROGRESSION + [S.REJECTED, S.REJECTED, S.WISHLIST]

        for i, company_name in enumerate(COMPANIES):
            slug = company_name.lower().replace(" ", "")
            company, _ = Company.objects.get_or_create(
                name=company_name, defaults={"website": f"https://{slug}.example.com"}
            )

            timeline = build_timeline(rng, rng.choice(possible_outcomes))
            final_status = timeline[-1] if timeline else S.WISHLIST
            applied_date = today - timedelta(days=rng.randint(10, 60)) if timeline else None

            application = Application.objects.create(
                owner=user,
                company=company,
                role_title=rng.choice(ROLES),
                status=final_status,
                applied_date=applied_date,
                job_url=f"https://{slug}.example.com/careers/{i}",
            )

            # One event per step, spaced a few days apart, never dated in the future.
            event_date = applied_date
            for step_number, status in enumerate(timeline):
                if step_number > 0:
                    event_date = min(event_date + timedelta(days=rng.randint(2, 9)), today)
                StatusEvent.objects.create(
                    application=application,
                    status=status,
                    changed_at=timezone.make_aware(datetime.combine(event_date, time(10, 0))),
                    note="Application submitted." if step_number == 0 else "",
                )

            if final_status in (S.INTERVIEWING, S.OFFER):
                Interview.objects.create(
                    application=application,
                    interview_type=rng.choice(Interview.Type.choices)[0],
                    scheduled_at=timezone.now() + timedelta(days=rng.randint(1, 10)),
                    notes="Scheduled via recruiter email.",
                )

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(COMPANIES)} demo applications for user 'demo'."))

"""Seed synthetic demo data (development / staging only).

    DEMO_PASSWORD=... python manage.py seed_demo

Refuses to run when DEBUG is off unless ``--allow-non-debug`` is passed (staging). The password
comes from the environment (``DEMO_PASSWORD`` in ``.env``); every demo account shares it.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.platform.demo_seed import seed


class Command(BaseCommand):
    help = "Create demo organisations, users per role and published vacancies (idempotent)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--allow-non-debug", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("seed_demo is for development; pass --allow-non-debug on staging.")
        password = os.environ.get("DEMO_PASSWORD", "")
        if not password:
            raise CommandError("Set DEMO_PASSWORD (see .env.example).")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        result = seed(password)
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"Organisations: {', '.join(result.organisations)}")
        self.stdout.write(f"Accounts ({len(result.users)}): {', '.join(result.users)}")
        self.stdout.write(f"New vacancies: {', '.join(result.jobs) or 'none (already seeded)'}")

"""Submit N synthetic applications to the demo Software Developer vacancy (development / CI).

    DEMO_PASSWORD=... python manage.py seed_demo
    DEMO_PASSWORD=... python manage.py seed_core_scenario --count 100

Used by the Playwright core scenario (``frontend/e2e/core-scenario.spec.ts``). Workers must be
running to extract and screen the applications.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.platform.core_scenario import seed


class Command(BaseCommand):
    help = "Submit synthetic applications for the end-to-end core scenario (idempotent)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--delay-minutes", type=int, default=None)
        parser.add_argument("--allow-non-debug", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("seed_core_scenario is for development and CI.")
        password = os.environ.get("DEMO_PASSWORD", "")
        if not password:
            raise CommandError("Set DEMO_PASSWORD (see .env.example).")
        try:
            result = seed(options["count"], password, delay_minutes=options["delay_minutes"])
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Submitted {len(result.submitted)} applications to {result.job_id} "
                f"({result.skipped} already submitted)."
            )
        )

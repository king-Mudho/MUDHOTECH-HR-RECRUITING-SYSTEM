"""Verified synthetic candidate accounts for the Locust load test (P10-T05; development/CI only).

    DEMO_PASSWORD=... python manage.py seed_load_accounts --count 1000

Accounts are ``load0001@load.test`` ... with the demo password. Idempotent.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.platform.core_scenario import daytime_zone
from apps.platform.demo_seed import _user


def load_email(i: int) -> str:
    return f"load{i:04d}@load.test"


class Command(BaseCommand):
    help = "Create verified synthetic candidates for load tests (idempotent)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--count", type=int, default=1000)
        parser.add_argument("--allow-non-debug", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("seed_load_accounts is for development and CI.")
        password = os.environ.get("DEMO_PASSWORD", "")
        if not password:
            raise CommandError("Set DEMO_PASSWORD (see .env.example).")
        zone = daytime_zone()
        for i in range(1, options["count"] + 1):
            _user(load_email(i), password, f"Load{i:04d}", "Synthetic", timezone=zone)
        self.stdout.write(self.style.SUCCESS(f"{options['count']} load-test candidates ready."))

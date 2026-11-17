"""Pilot benchmark: a new vacancy, N synthetic applications, wait, write an accounting table.

    DEMO_PASSWORD=... python manage.py seed_demo
    DEMO_PASSWORD=... python manage.py run_pilot_benchmark --count 100 --out PILOT.md
    ... run_pilot_benchmark --inline     # no workers: run the consumers in this process

Exits 1 when an application is missing or still waiting at the timeout.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.platform import pilot


class Command(BaseCommand):
    help = "Run the 100-application pilot benchmark and write docs/reports/PILOT_BENCHMARK.md."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--inline", action="store_true", help="Run consumers in-process")
        parser.add_argument("--timeout", type=float, default=1800.0, help="Seconds to wait")
        parser.add_argument("--out", default=None, help="Markdown report path")
        parser.add_argument("--allow-non-debug", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG and not options["allow_non_debug"]:
            raise CommandError("run_pilot_benchmark is for development, CI and staging.")
        password = os.environ.get("DEMO_PASSWORD", "")
        if not password:
            raise CommandError("Set DEMO_PASSWORD (see .env.example).")
        try:
            result, acc, text = pilot.run(
                options["count"],
                password,
                inline=options["inline"],
                timeout=options["timeout"],
                out=Path(options["out"]) if options["out"] else None,
            )
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(text)
        waiting = acc["statuses"].get("submitted", 0) + acc["statuses"].get("processing", 0)
        if acc["missing"] or result.timed_out or waiting:
            raise CommandError("Not every application was accounted for (see the report).")

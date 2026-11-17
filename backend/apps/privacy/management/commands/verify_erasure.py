"""Check that an erased person left no personal data behind (P09 exit criterion).

    python manage.py verify_erasure <user_id> --value "former@email" --value "Rudo" --value "Moyo"

Looks for the former identifiers in the tables that held them and for undeleted files. Exits 1 if
anything is found.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.privacy.erasure import residual_pii


class Command(BaseCommand):
    help = "Verify an erasure left no personal data (exit 1 when something remains)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("user_id")
        parser.add_argument("--value", action="append", default=[], help="A former identifier")

    def handle(self, *args: Any, **options: Any) -> None:
        found = residual_pii(options["user_id"], options["value"])
        if found:
            raise CommandError(f"Personal data remains: {found}")
        self.stdout.write(self.style.SUCCESS("No personal data found for this person."))

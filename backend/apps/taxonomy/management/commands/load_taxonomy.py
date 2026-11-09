from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.taxonomy.services import load_taxonomy


class Command(BaseCommand):
    help = "Load the platform skills/qualification taxonomy from fixtures (idempotent, versioned)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dir", help="Fixture directory (default backend/fixtures/taxonomy)")
        parser.add_argument("--force", action="store_true", help="Reload even if unchanged")

    def handle(self, *args: Any, **options: Any) -> None:
        result = load_taxonomy(
            Path(options["dir"]) if options["dir"] else None, force=options["force"]
        )
        if result.skipped:
            self.stdout.write(f"Taxonomy {result.version} already loaded - nothing to do.")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Loaded taxonomy {result.version}: {result.counts}")
            )

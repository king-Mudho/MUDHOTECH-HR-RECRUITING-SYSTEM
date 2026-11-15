from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.taxonomy.embeddings import embed_skills


class Command(BaseCommand):
    help = (
        "Precompute skill embeddings into the pgvector column (run in a worker container after "
        "load_taxonomy; only missing or other-model vectors are recomputed)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--force", action="store_true", help="Recompute every skill")
        parser.add_argument("--model", help=f"Model name (default {settings.EMBEDDING_MODEL})")

    def handle(self, *args: Any, **options: Any) -> None:
        count = embed_skills(force=options["force"], model=options["model"])
        self.stdout.write(self.style.SUCCESS(f"Embedded {count} skills."))

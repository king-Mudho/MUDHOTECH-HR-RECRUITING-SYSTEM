from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Send the core ping task to a worker and wait for 'pong' (smoke test)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--queue", default="default")
        parser.add_argument("--timeout", type=float, default=30.0)

    def handle(self, *args: Any, **options: Any) -> None:
        from config.celery import app

        result = app.send_task("apps.core.tasks.ping", queue=options["queue"])
        try:
            value = result.get(timeout=options["timeout"])
        except Exception as exc:
            raise CommandError(f"No pong within {options['timeout']}s: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Worker replied: {value}"))

from typing import Any

from django.core.management.base import BaseCommand

from apps.notifications.services import sync_platform_defaults


class Command(BaseCommand):
    help = "Create or refresh the platform default notification templates."

    def handle(self, *args: Any, **options: Any) -> None:
        result = sync_platform_defaults()
        self.stdout.write(
            f"Templates: {result['created']} new versions, {result['unchanged']} unchanged."
        )

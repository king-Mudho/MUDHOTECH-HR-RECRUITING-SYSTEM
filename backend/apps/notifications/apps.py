from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_defaults(sender: AppConfig, **kwargs: Any) -> None:
    from .services import sync_platform_defaults

    sync_platform_defaults()


class NotificationsConfig(AppConfig):
    name = "apps.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        post_migrate.connect(
            _sync_defaults, sender=self, dispatch_uid="notifications.sync_defaults"
        )

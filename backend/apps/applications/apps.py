from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_reasons(sender: AppConfig, **kwargs: Any) -> None:
    from .reasons import sync_default_reasons

    sync_default_reasons()


class ApplicationsConfig(AppConfig):
    name = "apps.applications"
    label = "applications"
    verbose_name = "Applications"

    def ready(self) -> None:
        post_migrate.connect(_sync_reasons, sender=self, dispatch_uid="applications.sync_reasons")
        from apps.documents.services import register_access_checker

        from . import tasks  # noqa: F401  registers the vacancy-event consumers
        from .hr import staff_can_access_document

        register_access_checker(staff_can_access_document)

from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_registry(sender: AppConfig, **kwargs: Any) -> None:
    from .registry import sync_registry

    sync_registry()


class ScreeningConfig(AppConfig):
    name = "apps.screening"
    label = "screening"
    verbose_name = "Screening"

    def ready(self) -> None:
        post_migrate.connect(_sync_registry, sender=self, dispatch_uid="screening.sync_registry")
        from . import tasks  # noqa: F401  registers the evidence consumers

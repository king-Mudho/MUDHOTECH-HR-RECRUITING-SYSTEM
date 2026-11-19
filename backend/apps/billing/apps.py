from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_plans(sender: AppConfig, **kwargs: Any) -> None:
    from .plans import seed_default_plans

    seed_default_plans()


class BillingConfig(AppConfig):
    name = "apps.billing"
    label = "billing"
    verbose_name = "Subscriptions and billing"

    def ready(self) -> None:
        post_migrate.connect(_seed_plans, sender=self, dispatch_uid="billing.seed_plans")
        from . import tasks  # noqa: F401  registers the metering consumers

from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"
    label = "integrations"
    verbose_name = "External integrations"

    def ready(self) -> None:
        from . import calendar_sync, messaging, webhooks  # noqa: F401  outbox consumers

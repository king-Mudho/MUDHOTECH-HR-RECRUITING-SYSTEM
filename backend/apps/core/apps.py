from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Core platform"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import email, signals  # noqa: F401  (registers signal handlers + consumers)

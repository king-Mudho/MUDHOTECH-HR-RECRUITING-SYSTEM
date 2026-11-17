from django.apps import AppConfig


class PrivacyConfig(AppConfig):
    name = "apps.privacy"
    label = "privacy"
    verbose_name = "Privacy & consent"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  registers the export consumer

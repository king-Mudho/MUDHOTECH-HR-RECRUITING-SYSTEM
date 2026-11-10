from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    name = "apps.applications"
    label = "applications"
    verbose_name = "Applications"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  registers the vacancy-event consumers

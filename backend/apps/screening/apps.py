from django.apps import AppConfig


class ScreeningConfig(AppConfig):
    name = "apps.screening"
    label = "screening"
    verbose_name = "Screening"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  registers the evidence consumers

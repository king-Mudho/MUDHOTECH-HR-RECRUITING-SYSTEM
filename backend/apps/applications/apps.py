from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    name = "apps.applications"
    label = "applications"
    verbose_name = "Applications"

    def ready(self) -> None:
        from apps.documents.services import register_access_checker

        from . import tasks  # noqa: F401  registers the vacancy-event consumers
        from .hr import staff_can_access_document

        register_access_checker(staff_can_access_document)

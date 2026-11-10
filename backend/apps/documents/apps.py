from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"
    verbose_name = "Documents"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  registers the document.uploaded consumer

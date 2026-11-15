from django.apps import AppConfig


class ResumesConfig(AppConfig):
    name = "apps.resumes"
    label = "resumes"
    verbose_name = "CV extraction"

    def ready(self) -> None:
        from . import tasks  # noqa: F401  registers the submission/document consumers

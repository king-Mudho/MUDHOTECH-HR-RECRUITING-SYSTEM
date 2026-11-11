from django.apps import AppConfig


class MessagingConfig(AppConfig):
    name = "apps.messaging"
    label = "messaging"
    verbose_name = "Clarifications & messages"

    def ready(self) -> None:
        from apps.documents.services import register_access_checker

        from . import tasks  # noqa: F401  registers consumers
        from .services import participant_can_access_document

        register_access_checker(participant_can_access_document)

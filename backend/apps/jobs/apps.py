from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.jobs"
    label = "jobs"
    verbose_name = "Vacancies"

    def ready(self) -> None:
        from apps.organisations.permissions import register_assignment_checker
        from apps.organisations.services import register_reassignment_provider

        from .assignments import is_assigned, needs_reassignment

        register_assignment_checker(is_assigned)
        register_reassignment_provider(needs_reassignment)

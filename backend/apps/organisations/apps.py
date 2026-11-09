from django.apps import AppConfig


class OrganisationsConfig(AppConfig):
    name = "apps.organisations"
    label = "organisations"
    verbose_name = "Organisations"

    def ready(self) -> None:
        from apps.accounts.mfa import register_privilege_provider

        from .services import user_has_privileged_membership

        # FR-M01-04: org_admin / hr_manager must use MFA.
        register_privilege_provider(user_has_privileged_membership)

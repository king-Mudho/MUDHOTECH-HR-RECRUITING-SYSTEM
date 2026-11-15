from django.contrib import admin

from .models import ExtractionRun


@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    """Operational view only: no CV text or claim payloads (personal data) in the admin."""

    list_display = (
        "id",
        "organisation",
        "status",
        "error_code",
        "engine_version",
        "claim_count",
        "attempts",
        "created_at",
    )
    list_filter = ("status", "engine_version")
    readonly_fields = [f.name for f in ExtractionRun._meta.fields if f.name not in ("id",)]
    search_fields = ("id", "application__reference")

    def has_add_permission(self, request: object) -> bool:
        return False

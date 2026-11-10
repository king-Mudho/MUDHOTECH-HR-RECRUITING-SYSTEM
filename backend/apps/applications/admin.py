from django.contrib import admin

from .models import Application, ApplicationStatusEvent


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference", "job", "candidate_user", "status", "submitted_at")
    list_filter = ("status",)
    search_fields = ("reference", "candidate_user__email")
    raw_id_fields = (
        "job",
        "job_version",
        "candidate_user",
        "assigned_recruiter",
        "assisted_by",
        "duplicate_of",
    )


@admin.register(ApplicationStatusEvent)
class ApplicationStatusEventAdmin(admin.ModelAdmin):
    list_display = ("application", "from_status", "to_status", "actor_type", "at")
    readonly_fields = [f.name for f in ApplicationStatusEvent._meta.fields]

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

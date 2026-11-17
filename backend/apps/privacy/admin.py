from django.contrib import admin

from .models import ConsentRecord, LegalHold, PrivacyNotice, RetentionRun, RightsRequest


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "granted", "notice_version", "granted_at", "withdrawn_at")
    list_filter = ("purpose", "granted")
    raw_id_fields = ("user", "organisation")
    readonly_fields = [f.name for f in ConsentRecord._meta.fields]


@admin.register(PrivacyNotice)
class PrivacyNoticeAdmin(admin.ModelAdmin):
    list_display = ("organisation", "version", "first_shown_at")
    readonly_fields = ("organisation", "version", "text", "first_shown_at")


@admin.register(RightsRequest)
class RightsRequestAdmin(admin.ModelAdmin):
    """Operational view; requests are handled in the HR/platform privacy workspace (audited)."""

    list_display = ("reference", "type", "status", "organisation", "due_at", "completed_at")
    list_filter = ("type", "status")
    exclude = ("details", "resolution", "statement", "verify_token_hash")

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False


@admin.register(RetentionRun)
class RetentionRunAdmin(admin.ModelAdmin):
    list_display = ("organisation", "started_at", "finished_at", "dry_run")
    readonly_fields = ("organisation", "started_at", "finished_at", "counts", "dry_run")


@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = ("organisation", "target_type", "target_id", "placed_at", "released_at")
    exclude = ("reason",)

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

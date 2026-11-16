from django.contrib import admin

from .models import Shortlist, ShortlistEntry


class EntryInline(admin.TabularInline):
    model = ShortlistEntry
    extra = 0
    can_delete = False
    fields = ("application", "suggestion", "decision", "reason_code", "override", "decided_by")
    readonly_fields = fields


@admin.register(Shortlist)
class ShortlistAdmin(admin.ModelAdmin):
    """Operational view only; decisions are made in the HR workspace (audited)."""

    list_display = ("id", "organisation", "job", "status", "desired_size", "approved_at")
    list_filter = ("status",)
    inlines = (EntryInline,)

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

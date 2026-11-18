from django.contrib import admin

from apps.core.admin import TenantAdminMixin

from .models import Interview, InterviewPanelist, InterviewSlot, Scorecard, ScorecardTemplate


class SlotInline(admin.TabularInline):
    model = InterviewSlot
    extra = 0
    readonly_fields = ("starts_at", "ends_at", "booked", "booked_at")


class PanelistInline(admin.TabularInline):
    model = InterviewPanelist
    extra = 0
    readonly_fields = ("membership", "role")


@admin.register(Interview)
class InterviewAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("stage", "mode", "status", "starts_at", "organisation")
    list_filter = ("status", "mode")
    readonly_fields = ("application", "created_by", "sequence", "lock_version")
    inlines = (SlotInline, PanelistInline)


@admin.register(ScorecardTemplate)
class ScorecardTemplateAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name", "job", "locked_at", "organisation")


@admin.register(Scorecard)
class ScorecardAdmin(TenantAdminMixin, admin.ModelAdmin):
    # scores and notes are candidate assessments: no content in the list view
    list_display = ("interview", "panelist", "submitted_at")
    readonly_fields = ("interview", "panelist", "template", "submitted_at")
    exclude = ("criterion_notes", "notes", "scores")

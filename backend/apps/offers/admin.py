from django.contrib import admin

from apps.core.admin import TenantAdminMixin

from .models import HireRecord, Offer, OfferApproval


class ApprovalInline(admin.TabularInline):
    model = OfferApproval
    extra = 0
    readonly_fields = ("approver", "round", "decision", "comment", "at")


@admin.register(Offer)
class OfferAdmin(TenantAdminMixin, admin.ModelAdmin):
    # salary and conditions are personal data: not in the list view
    list_display = ("pk", "status", "issued_at", "expires_at", "organisation")
    list_filter = ("status",)
    readonly_fields = ("application", "acceptance_meta", "letter_document", "lock_version")
    inlines = (ApprovalInline,)


@admin.register(HireRecord)
class HireRecordAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("application", "start_date", "recorded_at", "cancelled_at", "organisation")
    readonly_fields = ("application", "offer", "recorded_by", "recorded_at")

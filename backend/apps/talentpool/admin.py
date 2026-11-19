from django.contrib import admin

from apps.core.admin import TenantAdminMixin

from .models import TalentPoolEntry


@admin.register(TalentPoolEntry)
class TalentPoolEntryAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("pk", "status", "joined_at", "expires_at", "organisation")
    list_filter = ("status",)
    readonly_fields = [f.name for f in TalentPoolEntry._meta.fields]

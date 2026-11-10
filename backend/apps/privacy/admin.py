from django.contrib import admin

from .models import ConsentRecord


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "granted", "notice_version", "granted_at", "withdrawn_at")
    list_filter = ("purpose", "granted")
    raw_id_fields = ("user", "organisation")
    readonly_fields = [f.name for f in ConsentRecord._meta.fields]

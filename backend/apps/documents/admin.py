from django.contrib import admin

from .models import Document, UploadSession


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "owner_user",
        "purpose",
        "scan_status",
        "size_bytes",
        "created_at",
    )
    list_filter = ("purpose", "scan_status")
    search_fields = ("original_filename", "owner_user__email", "sha256")
    raw_id_fields = ("owner_user", "organisation", "duplicate_of")


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ("declared_name", "owner_user", "purpose", "status", "expires_at")
    list_filter = ("status", "purpose")
    raw_id_fields = ("owner_user", "organisation", "document")

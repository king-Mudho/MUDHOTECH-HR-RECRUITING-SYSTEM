from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import AccessLog, AuditEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "chain", "seq", "action", "actor", "target_type", "target_id")
    list_filter = ("action", "actor_type")
    search_fields = ("target_id", "request_id", "action")


@admin.register(AccessLog)
class AccessLogAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "user", "action", "target_type", "target_id")

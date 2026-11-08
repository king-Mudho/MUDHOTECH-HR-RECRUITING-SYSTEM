from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import DeadLetter, FeatureFlag, IdempotencyKey, OutboxEvent


class TenantAdminMixin:
    """Platform-staff admin views are deliberately cross-tenant: mark the queryset as vetted."""

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        return super().get_queryset(request).unscoped()  # type: ignore[misc]


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "status",
        "attempts",
        "created_at",
    )
    list_filter = ("status", "event_type")
    search_fields = ("aggregate_id", "dedupe_key")
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("key", "organisation", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("key",)


@admin.register(DeadLetter)
class DeadLetterAdmin(admin.ModelAdmin):
    list_display = ("task_name", "task_id", "created_at", "resolved_at")
    list_filter = ("task_name",)
    readonly_fields = ("task_name", "task_id", "args", "kwargs", "error", "traceback", "request_id")


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "key", "user", "response_status", "expires_at")
    readonly_fields = [f.name for f in IdempotencyKey._meta.fields]

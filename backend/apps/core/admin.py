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


class UnresolvedFilter(admin.SimpleListFilter):
    title = "state"
    parameter_name = "state"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        return [("open", "Open"), ("resolved", "Resolved")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.value() == "open":
            return queryset.filter(resolved_at__isnull=True)
        if self.value() == "resolved":
            return queryset.filter(resolved_at__isnull=False)
        return queryset


@admin.register(DeadLetter)
class DeadLetterAdmin(admin.ModelAdmin):
    """EC-OPS-07: inspect, retry (tasks are idempotent) or resolve failed tasks; audited."""

    list_display = ("task_name", "task_id", "created_at", "resolved_at", "resolved_by")
    list_filter = (UnresolvedFilter, "task_name")
    readonly_fields = (
        "task_name",
        "task_id",
        "args",
        "kwargs",
        "error",
        "traceback",
        "request_id",
        "organisation_id",
        "resolved_at",
        "resolved_by",
    )
    actions = ("retry_selected", "resolve_selected")

    @admin.action(description="Retry selected tasks (queue them again)")
    def retry_selected(self, request: HttpRequest, queryset: QuerySet[DeadLetter]) -> None:
        from .deadletters import retry

        done = sum(retry(dl, request.user) for dl in queryset)
        self.message_user(
            request, f"{done} task(s) queued again; {queryset.count() - done} skipped."
        )

    @admin.action(description="Mark selected as resolved without retrying")
    def resolve_selected(self, request: HttpRequest, queryset: QuerySet[DeadLetter]) -> None:
        from .deadletters import resolve

        done = sum(resolve(dl, request.user, "resolved in admin") for dl in queryset)
        self.message_user(request, f"{done} dead letter(s) resolved.")


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "key", "user", "response_status", "expires_at")
    readonly_fields = [f.name for f in IdempotencyKey._meta.fields]

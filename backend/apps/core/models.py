"""Core platform models: base classes, tenancy guard, outbox, idempotency, flags, dead letters."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Self

from django.conf import settings
from django.db import models
from django.db.models.lookups import Lookup
from django.db.models.sql.where import WhereNode

from .context import tenant_guard_var

if TYPE_CHECKING:
    from apps.organisations.models import Organisation


class BaseModel(models.Model):
    """UUID primary key + created/updated timestamps (docs/03 conventions)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


# --------------------------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------------------------
class UnscopedTenantQueryError(RuntimeError):
    """Raised (strict mode, in a request) when a tenant queryset is evaluated without scoping."""


def _where_filters_org(node: WhereNode) -> bool:
    for child in node.children:
        if isinstance(child, WhereNode):
            if child.connector == "AND" and not child.negated and _where_filters_org(child):
                return True
        elif isinstance(child, Lookup):
            target = getattr(child.lhs, "target", None)
            if getattr(target, "attname", None) == "organisation_id" and child.lookup_name in (
                "exact",
                "in",
            ):
                return True
    return False


class TenantQuerySet(models.QuerySet):
    """QuerySet that knows whether it has been scoped to an organisation.

    ``for_org(org)`` is the canonical way to scope. A queryset filtered on ``organisation`` (e.g.
    via a related manager ``org.jobs``) also counts as scoped. ``unscoped()`` is an explicit,
    greppable escape hatch for system code (relays, retention jobs, platform admin).
    """

    _mhrs_scoped: bool = False

    def _clone(self) -> Self:
        clone = super()._clone()  # type: ignore[misc]
        clone._mhrs_scoped = self._mhrs_scoped
        return clone

    def for_org(self, org: Organisation | uuid.UUID | str) -> Self:
        org_id = getattr(org, "pk", org)
        if org_id is None:
            raise ValueError("for_org() requires an organisation.")
        qs = self.filter(organisation_id=org_id)
        qs._mhrs_scoped = True
        return qs

    def unscoped(self) -> Self:
        qs = self._clone()
        qs._mhrs_scoped = True
        return qs

    @property
    def is_scoped(self) -> bool:
        return (
            self._mhrs_scoped
            or _where_filters_org(self.query.where)
            or self._reached_from_tenant_instance()
        )

    def _reached_from_tenant_instance(self) -> bool:
        """Related managers / prefetches of an already-loaded tenant object (``job.versions``,
        ``version.criteria``) are scoped by that object: it could only have been loaded through
        a scoped query, and services keep children in their parent's organisation."""
        instance = getattr(self, "_hints", {}).get("instance")
        return isinstance(instance, TenantModel) and instance.organisation_id is not None

    def _guard(self) -> None:
        if (
            getattr(settings, "TENANT_STRICT_MODE", False)
            and tenant_guard_var.get()
            and not self.is_scoped
        ):
            raise UnscopedTenantQueryError(
                f"Unscoped query on tenant model {self.model.__name__}: use "
                f".for_org(request.organisation) (or .unscoped() for vetted system code)."
            )

    def _fetch_all(self) -> None:
        if self._result_cache is None:
            self._guard()
        super()._fetch_all()

    def count(self) -> int:
        self._guard()
        return super().count()

    def exists(self) -> bool:
        self._guard()
        return super().exists()

    def iterator(self, chunk_size: int | None = None) -> Any:
        self._guard()
        return super().iterator(chunk_size=chunk_size)

    def aggregate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._guard()
        return super().aggregate(*args, **kwargs)

    def update(self, **kwargs: Any) -> int:
        self._guard()
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        self._guard()
        return super().delete()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    pass


class TenantModel(BaseModel):
    """Base for every organisation-owned row. Always query via ``Model.objects.for_org(org)``."""

    organisation = models.ForeignKey(
        "organisations.Organisation", on_delete=models.PROTECT, related_name="+", db_index=True
    )

    objects = TenantManager()

    class Meta:
        abstract = True
        ordering = ("-created_at",)


# --------------------------------------------------------------------------------------------
# Transactional outbox (ADR-006, docs/02 §5.3)
# --------------------------------------------------------------------------------------------
class OutboxEvent(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    event_type = models.CharField(max_length=100)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=64)
    organisation_id = models.UUIDField(null=True, blank=True, db_index=True)
    payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=["status", "available_at"], name="outbox_status_avail_idx")]

    def __str__(self) -> str:
        return f"{self.event_type}:{self.aggregate_id} [{self.status}]"


class ProcessedEvent(models.Model):
    """Consumer-side idempotency record: one row per (consumer, event)."""

    id = models.BigAutoField(primary_key=True)
    consumer = models.CharField(max_length=100)
    event_id = models.UUIDField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["consumer", "event_id"], name="uniq_consumer_event")
        ]

    def __str__(self) -> str:
        return f"{self.consumer}:{self.event_id}"


# --------------------------------------------------------------------------------------------
# Idempotency keys (docs/04 §1)
# --------------------------------------------------------------------------------------------
class IdempotencyKey(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    key = models.CharField(max_length=128)
    endpoint = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key", "endpoint"],
                name="uniq_idempotency_user_key_endpoint",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.endpoint}:{self.key}"


# --------------------------------------------------------------------------------------------
# Feature flags
# --------------------------------------------------------------------------------------------
class FeatureFlag(BaseModel):
    key = models.CharField(max_length=100)
    enabled = models.BooleanField(default=False)
    organisation = models.ForeignKey(
        "organisations.Organisation",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feature_flags",
        help_text="Null = global default; set = per-organisation override.",
    )
    rollout = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ("key",)
        constraints = [
            models.UniqueConstraint(
                fields=["key", "organisation"], name="uniq_flag_key_org", nulls_distinct=False
            )
        ]

    def __str__(self) -> str:
        scope = self.organisation_id or "global"
        return f"{self.key}@{scope}={'on' if self.enabled else 'off'}"


# --------------------------------------------------------------------------------------------
# Dead letters
# --------------------------------------------------------------------------------------------
class DeadLetter(BaseModel):
    task_name = models.CharField(max_length=200)
    task_id = models.CharField(max_length=64, blank=True, default="")
    args = models.JSONField(default=list, blank=True)
    kwargs = models.JSONField(default=dict, blank=True)
    error = models.TextField()
    traceback = models.TextField(blank=True, default="")
    organisation_id = models.UUIDField(null=True, blank=True, db_index=True)
    request_id = models.CharField(max_length=128, blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return f"{self.task_name} ({self.task_id})"

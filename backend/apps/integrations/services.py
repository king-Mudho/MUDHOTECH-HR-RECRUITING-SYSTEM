"""Integration connections: connect, rotate credentials, disconnect, health and failure isolation
(P15-T01, M21 AC "failures never affect core records").

``call(connection, fn)`` runs an adapter call and records the outcome on the connection (health);
any provider error is caught, recorded and returned as ``None`` - callers (outbox consumers) carry
on and core records are never touched by an integration failure. After
``FAILURES_BEFORE_ERROR`` consecutive failures the connection shows as failing and its admins are
told once.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from django.db import IntegrityError, transaction
from django.utils.module_loading import import_string

from apps.audit import services as audit
from apps.core.exceptions import ConflictError, DomainError, NotFoundError
from apps.core.time import now

from . import registry
from .adapters.base import BaseAdapter, IntegrationError
from .models import ConnectionStatus, IntegrationConnection

FAILURES_BEFORE_ERROR = 3


def _hint(credentials: dict[str, Any]) -> str:
    for value in credentials.values():
        text = str(value)
        if len(text) >= 8:
            return f"…{text[-4:]}"
    return "set"


def _clean(
    provider: registry.Provider, credentials: dict[str, Any], config: dict[str, Any]
) -> None:
    missing = [f for f in provider.credential_fields if not str(credentials.get(f, "")).strip()]
    if missing:
        raise DomainError(
            "validation_error",
            "Some credentials are missing.",
            details={"credentials": [f"Required: {', '.join(missing)}"]},
        )
    unknown = set(config) - set(provider.config_fields)
    if unknown:
        raise DomainError(
            "validation_error",
            "Unknown settings.",
            details={"config": [f"Unknown: {', '.join(sorted(unknown))}"]},
        )


def connect(
    membership: Any,
    provider_key: str,
    *,
    credentials: dict[str, Any],
    config: dict[str, Any] | None = None,
    sandbox: bool = False,
) -> IntegrationConnection:
    try:
        provider = registry.get(provider_key)
    except KeyError as exc:
        raise NotFoundError() from exc
    config = config or {}
    _clean(provider, credentials, config)
    owner = membership.user if provider.per_user else None
    try:
        with transaction.atomic():
            conn = IntegrationConnection.objects.create(
                organisation_id=membership.organisation_id,
                provider=provider.key,
                owner_user=owner,
                credentials=json.dumps(credentials),
                credentials_hint=_hint(credentials),
                config=config,
                sandbox=sandbox,
                credentials_rotated_at=now(),
                created_by=membership.user,
            )
            audit.record(
                actor=membership.user,
                action="integrations.connected",
                target=conn,
                organisation=membership.organisation_id,
                after={"provider": provider.key, "sandbox": sandbox, "per_user": provider.per_user},
            )
    except IntegrityError as exc:
        raise ConflictError(
            code="conflict.integration_exists", message=f"{provider.name} is already connected."
        ) from exc
    return conn


def visible(membership: Any) -> Any:
    """Organisation-wide connections plus the member's own per-person ones."""
    from django.db.models import Q

    return IntegrationConnection.objects.for_org(membership.organisation_id).filter(
        Q(owner_user__isnull=True) | Q(owner_user=membership.user)
    )


def _own(membership: Any, connection_id: Any, *, manage: bool) -> IntegrationConnection:
    from apps.organisations import rbac

    conn = visible(membership).filter(pk=connection_id).first()
    if conn is None:
        raise NotFoundError()
    if (
        conn.owner_user_id is None
        and manage
        and not rbac.can(membership.role, "integrations.manage")
    ):
        from apps.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError()
    return conn


def rotate(
    membership: Any, connection_id: Any, credentials: dict[str, Any]
) -> IntegrationConnection:
    conn = _own(membership, connection_id, manage=True)
    _clean(registry.get(conn.provider), credentials, conn.config or {})
    with transaction.atomic():
        conn.credentials = json.dumps(credentials)
        conn.credentials_hint = _hint(credentials)
        conn.credentials_rotated_at = now()
        conn.status = ConnectionStatus.ACTIVE
        conn.consecutive_failures = 0
        conn.save()
        audit.record(
            actor=membership.user,
            action="integrations.credentials_rotated",
            target=conn,
            organisation=membership.organisation_id,
        )
    return conn


def disconnect(membership: Any, connection_id: Any) -> None:
    conn = _own(membership, connection_id, manage=True)
    audit.record(
        actor=membership.user,
        action="integrations.disconnected",
        target=conn,
        organisation=membership.organisation_id,
        before={"provider": conn.provider},
    )
    conn.delete()


def adapter_for(conn: IntegrationConnection) -> BaseAdapter:
    provider = registry.get(conn.provider)
    cls = import_string(provider.adapter)
    try:
        credentials = json.loads(conn.credentials or "{}")
    except ValueError:
        credentials = {}
    return cls(conn, credentials)


def call[T](conn: IntegrationConnection, fn: Callable[[BaseAdapter], T]) -> T | None:
    """Run an adapter call with health recording; provider failures never propagate."""
    if conn.status == ConnectionStatus.DISABLED:
        return None
    try:
        result = fn(adapter_for(conn))
    except IntegrationError as exc:
        _failed(conn, str(exc))
        return None
    IntegrationConnection.objects.unscoped().filter(pk=conn.pk).update(
        status=ConnectionStatus.ACTIVE,
        last_success_at=now(),
        consecutive_failures=0,
    )
    return result


def _failed(conn: IntegrationConnection, message: str) -> None:
    failures = conn.consecutive_failures + 1
    status = ConnectionStatus.ERROR if failures >= FAILURES_BEFORE_ERROR else conn.status
    IntegrationConnection.objects.unscoped().filter(pk=conn.pk).update(
        last_error_at=now(),
        last_error=message[:300],
        consecutive_failures=failures,
        status=status,
    )
    conn.consecutive_failures = failures
    conn.status = status
    audit.record(
        actor=None,
        actor_type="system",
        action="integrations.call_failed",
        target=conn,
        organisation=conn.organisation_id,
        after={"error": message[:300], "consecutive_failures": failures},
    )


def test_connection(membership: Any, connection_id: Any) -> IntegrationConnection:
    conn = _own(membership, connection_id, manage=False)
    call(conn, lambda adapter: adapter.ping())
    conn.refresh_from_db()
    return conn


def org_connection(organisation_id: Any, provider: str) -> IntegrationConnection | None:
    return (
        IntegrationConnection.objects.for_org(organisation_id)
        .filter(provider=provider, owner_user__isnull=True)
        .exclude(status=ConnectionStatus.DISABLED)
        .first()
    )


def user_connections(organisation_id: Any, user_ids: list[Any], kind: str) -> list[Any]:
    providers = [p.key for p in registry.PROVIDERS.values() if p.kind == kind and p.per_user]
    return list(
        IntegrationConnection.objects.for_org(organisation_id)
        .filter(provider__in=providers, owner_user_id__in=user_ids)
        .exclude(status=ConnectionStatus.DISABLED)
    )

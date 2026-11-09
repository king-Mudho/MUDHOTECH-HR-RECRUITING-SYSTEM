"""Audit service: ``record()`` for sensitive actions, ``log_access()`` for PII views."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Model
from django.http import HttpRequest

from apps.core.context import get_request_id

from .models import PLATFORM_CHAIN, AccessLog, ActorType, AuditEvent

GENESIS = "0" * 64
SENSITIVE_KEYS = frozenset(
    {"password", "token", "token_hash", "secret", "key", "code", "recovery_codes", "totp"}
)


def minimise(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop secrets from before/after snapshots (data minimisation)."""
    if data is None:
        return None
    return {k: ("[redacted]" if k.lower() in SENSITIVE_KEYS else v) for k, v in data.items()}


def truncate_ip(raw: str | None) -> str:
    """IPv4 -> /24, IPv6 -> /48 (privacy-preserving)."""
    if not raw:
        return ""
    try:
        ip = ipaddress.ip_address(raw.split(",")[0].strip())
    except ValueError:
        return ""
    prefix = 24 if ip.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


def hash_user_agent(ua: str | None) -> str:
    return hashlib.sha256(ua.encode()).hexdigest()[:32] if ua else ""


def _canonical(event: AuditEvent) -> str:
    payload = {
        "chain": event.chain,
        "seq": event.seq,
        "organisation_id": str(event.organisation_id) if event.organisation_id else None,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "actor_type": event.actor_type,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "before": event.before,
        "after": event.after,
        "reason": event.reason,
        "ip_trunc": event.ip_trunc,
        "user_agent_hash": event.user_agent_hash,
        "request_id": event.request_id,
        "at": event.created_at.isoformat(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), cls=DjangoJSONEncoder)


def compute_hash(event: AuditEvent) -> str:
    return hashlib.sha256((_canonical(event) + event.prev_hash).encode()).hexdigest()


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))  # type: ignore[no-any-return]


def record(
    *,
    actor: Any = None,
    action: str,
    target: Model | tuple[str, Any] | None = None,
    organisation: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
    request: HttpRequest | None = None,
    actor_type: str | None = None,
) -> AuditEvent:
    """Append an audit event to the organisation's (or platform) chain.

    Runs in its own atomic block (joins the caller's transaction if any, so the event commits or
    rolls back with the business change). Chains are serialised with a transaction-level advisory
    lock, so concurrent writers never fork a chain.
    """
    if isinstance(target, Model):
        target_type, target_id = target._meta.label_lower, str(target.pk)
        if organisation is None:
            organisation = getattr(target, "organisation_id", None) or (
                target.pk if target._meta.label_lower == "organisations.organisation" else None
            )
    elif target is not None:
        target_type, target_id = target[0], str(target[1])
    else:
        target_type, target_id = "", ""

    org_id = getattr(organisation, "pk", organisation)
    chain = str(org_id) if org_id else PLATFORM_CHAIN
    if actor is not None and not getattr(actor, "is_authenticated", True):
        actor = None
    if actor_type is None:
        actor_type = ActorType.HUMAN if actor is not None else ActorType.SYSTEM

    meta = request.META if request is not None else {}
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"audit:{chain}"])
        last = AuditEvent.objects.filter(chain=chain).order_by("-seq").only("seq", "hash").first()
        event = AuditEvent(
            id=uuid.uuid4(),
            chain=chain,
            seq=(last.seq + 1) if last else 1,
            organisation_id=org_id,
            actor=actor,
            actor_type=actor_type,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=_json_safe(minimise(before)),
            after=_json_safe(minimise(after)),
            reason=reason or "",
            ip_trunc=truncate_ip(meta.get("REMOTE_ADDR")),
            user_agent_hash=hash_user_agent(meta.get("HTTP_USER_AGENT")),
            request_id=get_request_id() or "",
            prev_hash=last.hash if last else GENESIS,
        )
        event.hash = compute_hash(event)  # created_at was set by the field default
        event.save(force_insert=True)
    return event


def log_access(
    *, user: Any, target: Model | tuple[str, Any], organisation: Any = None, action: str = "view"
) -> AccessLog:
    if isinstance(target, Model):
        target_type, target_id = target._meta.label_lower, str(target.pk)
    else:
        target_type, target_id = target[0], str(target[1])
    return AccessLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        organisation_id=getattr(organisation, "pk", organisation),
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=get_request_id() or "",
    )


@dataclass(frozen=True)
class ChainBreak:
    chain: str
    seq: int
    reason: str


def iter_chains() -> Iterable[str]:
    return AuditEvent.objects.values_list("chain", flat=True).distinct().order_by("chain")


def verify_chain(chain: str) -> Iterator[ChainBreak]:
    prev = GENESIS
    expected_seq = 1
    for event in AuditEvent.objects.filter(chain=chain).order_by("seq").iterator():
        if event.seq != expected_seq:
            yield ChainBreak(chain, event.seq, f"sequence gap (expected {expected_seq})")
        if event.prev_hash != prev:
            yield ChainBreak(chain, event.seq, "prev_hash does not match previous event")
        if compute_hash(event) != event.hash:
            yield ChainBreak(chain, event.seq, "hash mismatch (event content altered)")
        prev = event.hash
        expected_seq = event.seq + 1

"""Outbound webhooks (P15-T05, docs/03 webhook_endpoints / webhook_deliveries).

* Organisation admins register HTTPS endpoints and choose events.
* Each subscribed outbox event becomes a ``WebhookDelivery`` (exactly once per endpoint and event)
  sent as JSON with ``X-MHRS-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>``.
* Failed deliveries are retried with backoff (1 min, 5 min, 30 min, 2 h, 6 h, 12 h) and then marked
  failed; admins can replay any delivery from the log.
* Payloads carry identifiers and statuses only - no names, emails or documents (data
  minimisation); receivers fetch details through the API with their own key.
* SSRF protection: only ``https://`` URLs whose host resolves to public addresses are called.
* A failing receiver never affects core records: deliveries run after commit, on their own queue.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.models import OutboxEvent
from apps.core.outbox import idempotent_consumer
from apps.core.time import now

from .adapters.base import SANDBOX_OUTBOX
from .models import DeliveryStatus, WebhookDelivery, WebhookEndpoint

EVENTS = (
    "application.submitted",
    "application.status_changed",
    "shortlist.approved",
    "offer.accepted",
    "job.published",
)
BACKOFF = (60, 300, 1800, 7200, 21600, 43200)
MAX_ATTEMPTS = len(BACKOFF) + 1
TIMEOUT = 10
PAYLOAD_KEYS = (
    "application_id",
    "job_id",
    "job_version_id",
    "reference",
    "from",
    "to",
    "status",
    "shortlist_id",
    "offer_id",
    "version",
)


# --- signing ------------------------------------------------------------------------------------
def sign(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    """Reference receiver-side check (also shown in docs/integrations/webhooks.md)."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:
        return False
    expected = sign(secret, body, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


# --- endpoints ----------------------------------------------------------------------------------
def _public_host(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise DomainError("validation_error", "Use an https:// URL.", details={"url": ["https"]})
    host = parsed.hostname.lower()
    try:
        literal = [ipaddress.ip_address(host)]
    except ValueError:
        literal = []
    # literal addresses and localhost are refused in every mode, so sandbox behaves like production
    if host == "localhost" or host.endswith(".localhost"):
        _refuse_private()
    if literal:
        addresses = literal
    elif settings.INTEGRATIONS_SANDBOX:
        return  # no DNS lookups in sandbox mode: nothing is called
    else:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443)
        except OSError as exc:
            raise DomainError("validation_error", "The host could not be resolved.") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    for ip in addresses:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            _refuse_private()


def _refuse_private() -> None:
    raise DomainError(
        "validation_error",
        "Webhook URLs must point to a public address.",
        details={"url": ["Private or local addresses are not allowed."]},
    )


def create_endpoint(
    membership: Any, *, url: str, events: list[str], description: str = ""
) -> tuple[WebhookEndpoint, str]:
    unknown = set(events) - set(EVENTS)
    if not events or unknown:
        raise DomainError(
            "validation_error",
            "Choose at least one supported event.",
            details={"events": [f"Supported: {', '.join(EVENTS)}"]},
        )
    _public_host(url)
    secret = "whsec_" + secrets.token_urlsafe(32)
    with transaction.atomic():
        endpoint = WebhookEndpoint.objects.create(
            organisation_id=membership.organisation_id,
            url=url,
            secret=secret,
            events=sorted(set(events)),
            description=description[:200],
            created_by=membership.user,
        )
        audit.record(
            actor=membership.user,
            action="webhooks.endpoint_created",
            target=endpoint,
            organisation=membership.organisation_id,
            after={"url": url, "events": endpoint.events},
        )
    return endpoint, secret  # the secret is shown once


def rotate_secret(membership: Any, endpoint_id: Any) -> tuple[WebhookEndpoint, str]:
    endpoint = _endpoint(membership, endpoint_id)
    secret = "whsec_" + secrets.token_urlsafe(32)
    endpoint.secret = secret
    endpoint.save(update_fields=["secret", "updated_at"])
    audit.record(
        actor=membership.user,
        action="webhooks.secret_rotated",
        target=endpoint,
        organisation=membership.organisation_id,
    )
    return endpoint, secret


def update_endpoint(membership: Any, endpoint_id: Any, **changes: Any) -> WebhookEndpoint:
    endpoint = _endpoint(membership, endpoint_id)
    if "events" in changes:
        unknown = set(changes["events"]) - set(EVENTS)
        if not changes["events"] or unknown:
            raise DomainError("validation_error", "Choose supported events.")
        endpoint.events = sorted(set(changes["events"]))
    if "active" in changes:
        endpoint.active = bool(changes["active"])
    endpoint.save(update_fields=["events", "active", "updated_at"])
    audit.record(
        actor=membership.user,
        action="webhooks.endpoint_updated",
        target=endpoint,
        organisation=membership.organisation_id,
        after={"events": endpoint.events, "active": endpoint.active},
    )
    return endpoint


def delete_endpoint(membership: Any, endpoint_id: Any) -> None:
    endpoint = _endpoint(membership, endpoint_id)
    audit.record(
        actor=membership.user,
        action="webhooks.endpoint_deleted",
        target=endpoint,
        organisation=membership.organisation_id,
        before={"url": endpoint.url},
    )
    endpoint.delete()


def _endpoint(membership: Any, endpoint_id: Any) -> WebhookEndpoint:
    endpoint = (
        WebhookEndpoint.objects.for_org(membership.organisation_id).filter(pk=endpoint_id).first()
    )
    if endpoint is None:
        raise NotFoundError()
    return endpoint


# --- delivery -----------------------------------------------------------------------------------
def payload_for(event: OutboxEvent) -> dict[str, Any]:
    data = {k: v for k, v in (event.payload or {}).items() if k in PAYLOAD_KEYS}
    return {
        "id": str(event.pk),
        "type": event.event_type,
        "created_at": event.created_at.isoformat(),
        "organisation_id": str(event.organisation_id),
        "data": data,
    }


def enqueue(event: OutboxEvent) -> int:
    if not event.organisation_id or event.event_type not in EVENTS:
        return 0
    created = 0
    for endpoint in WebhookEndpoint.objects.for_org(event.organisation_id).filter(active=True):
        if event.event_type not in (endpoint.events or []):
            continue
        try:
            with transaction.atomic():
                delivery = WebhookDelivery.objects.create(
                    organisation_id=event.organisation_id,
                    endpoint=endpoint,
                    event_id=event.pk,
                    event_type=event.event_type,
                    payload=payload_for(event),
                    next_attempt_at=now(),
                )
        except IntegrityError:
            continue  # already queued for this endpoint (redelivered event)
        attempt(delivery.pk)
        created += 1
    return created


def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    if settings.INTEGRATIONS_SANDBOX:
        SANDBOX_OUTBOX.append({"provider": "webhook", "method": "POST", "url": url, "body": body})
        return 200
    _public_host(url)  # re-checked at send time (DNS may change)
    req = urllib.request.Request(  # noqa: S310 - https + public host enforced above
        url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310  # nosec B310 - https, public host
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def attempt(delivery_id: Any) -> WebhookDelivery:
    with transaction.atomic():
        d = (
            WebhookDelivery.objects.unscoped()  # delivery worker: system context
            .select_for_update()
            .select_related("endpoint")
            .get(pk=delivery_id)
        )
        if d.status == DeliveryStatus.SUCCEEDED:
            return d
        body = json.dumps(d.payload, separators=(",", ":"), sort_keys=True).encode()
        ts = int(time.time())
        headers = {
            "X-MHRS-Signature": sign(d.endpoint.secret, body, ts),
            "X-MHRS-Event": d.event_type,
            "X-MHRS-Delivery": str(d.pk),
            "User-Agent": "MHRS-Webhooks/1.0",
        }
        d.attempts += 1
        try:
            code = _post(d.endpoint.url, body, headers)
            error = "" if 200 <= code < 300 else f"HTTP {code}"
        except (OSError, DomainError) as exc:
            code, error = 0, str(exc)[:200] or type(exc).__name__
        d.response_code = code or None
        if not error:
            d.status = DeliveryStatus.SUCCEEDED
            d.delivered_at = now()
            d.next_attempt_at = None
            d.last_error = ""
        else:
            d.last_error = error
            if d.attempts >= MAX_ATTEMPTS:
                d.status = DeliveryStatus.FAILED
                d.next_attempt_at = None
            else:
                d.status = DeliveryStatus.PENDING
                d.next_attempt_at = now() + timedelta(seconds=BACKOFF[d.attempts - 1])
        d.save()
    return d


def retry_due() -> int:
    due = WebhookDelivery.objects.unscoped().filter(
        status=DeliveryStatus.PENDING, next_attempt_at__lte=now()
    )
    count = 0
    for pk in due.values_list("pk", flat=True)[:200]:
        attempt(pk)
        count += 1
    return count


def replay(membership: Any, delivery_id: Any) -> WebhookDelivery:
    d = WebhookDelivery.objects.for_org(membership.organisation_id).filter(pk=delivery_id).first()
    if d is None:
        raise NotFoundError()
    WebhookDelivery.objects.for_org(membership.organisation_id).filter(pk=d.pk).update(
        status=DeliveryStatus.PENDING, attempts=0, next_attempt_at=now()
    )
    audit.record(
        actor=membership.user,
        action="webhooks.delivery_replayed",
        target=d,
        organisation=membership.organisation_id,
    )
    return attempt(d.pk)


@idempotent_consumer("integrations.webhooks", events=list(EVENTS))
def on_event(event: OutboxEvent) -> None:
    enqueue(event)

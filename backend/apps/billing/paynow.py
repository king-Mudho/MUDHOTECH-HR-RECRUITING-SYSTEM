"""Paynow client (P14-T06, ADR-015).

Implements Paynow's HTTP integration (form-encoded requests and responses) without an SDK:

* web checkout ``/initiatetransaction`` (cards and every method on Paynow's page) returns a
  ``browserurl`` to send the payer to and a ``pollurl``;
* mobile express ``/remotetransaction`` (EcoCash, OneMoney) pushes a prompt to the payer's phone;
* status polling (``pollurl``) and the result-URL callback carry the same fields.

Every message is signed: SHA-512 over the field values in order (``hash`` excluded) followed by the
integration key, upper-case hex. Incoming messages are verified before anything is trusted
(EC-BIL-01). Integration id/key are per currency and come from the environment; live keys are
supplied by the owner (Phase 14 STOP condition) - tests use a fake transport.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.core.exceptions import DomainError

Transport = Callable[[str, dict[str, str]], str]


class PaynowNotConfiguredError(DomainError):
    def __init__(self, currency: str) -> None:
        super().__init__(
            "payments_unavailable",
            f"Online payment in {currency} is not available yet. Please pay by bank transfer.",
            503,
        )


class PaynowError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__("payment_provider_error", message, 502)


@dataclass(frozen=True)
class Integration:
    id: str
    key: str


def integration(currency: str) -> Integration:
    conf = (settings.PAYNOW_INTEGRATIONS or {}).get(currency) or {}
    if not conf.get("id") or not conf.get("key"):
        raise PaynowNotConfiguredError(currency)
    return Integration(id=str(conf["id"]), key=str(conf["key"]))


def make_hash(values: list[tuple[str, str]], key: str) -> str:
    raw = "".join(str(v) for k, v in values if k.lower() != "hash") + key
    return hashlib.sha512(raw.encode("utf-8")).hexdigest().upper()


def verify(fields: list[tuple[str, str]], key: str) -> bool:
    given = next((v for k, v in fields if k.lower() == "hash"), "")
    return bool(given) and hmac.compare_digest(given.upper(), make_hash(fields, key))


def parse(body: str) -> list[tuple[str, str]]:
    return urllib.parse.parse_qsl(body.strip(), keep_blank_values=True)


def _http_post(url: str, data: dict[str, str]) -> str:
    if not url.startswith("https://"):
        raise PaynowError("Paynow URLs must use HTTPS.")
    request = urllib.request.Request(  # noqa: S310 - https only (checked above)
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=settings.PAYNOW_TIMEOUT_SECONDS) as resp:  # noqa: S310 - fixed https endpoints
        return str(resp.read().decode("utf-8"))


_transport: Transport = _http_post


def set_transport(fn: Transport | None) -> None:
    """Tests replace the network call; ``None`` restores the real one."""
    global _transport
    _transport = fn or _http_post


def _send(url: str, fields: list[tuple[str, str]], key: str) -> dict[str, str]:
    payload = dict(fields)
    payload["hash"] = make_hash(fields, key)
    try:
        body = _transport(url, payload)
    except OSError as exc:
        raise PaynowError("Paynow could not be reached. Please try again.") from exc
    reply = parse(body)
    data = {k.lower(): v for k, v in reply}
    if data.get("status", "").lower() == "error":
        raise PaynowError(f"Paynow refused the payment: {data.get('error', 'unknown error')}")
    if not verify(reply, key):
        raise PaynowError("Paynow's reply could not be verified.")
    return data


def initiate(
    currency: str,
    *,
    reference: str,
    amount: str,
    description: str,
    email: str,
    return_url: str,
    result_url: str,
    phone: str | None = None,
    method: str | None = None,
) -> dict[str, str]:
    """Start a payment; returns Paynow's verified reply (``browserurl``/``pollurl``/
    ``instructions``)."""
    conf = integration(currency)
    fields = [
        ("id", conf.id),
        ("reference", reference),
        ("amount", amount),
        ("additionalinfo", description[:100]),
        ("returnurl", return_url),
        ("resulturl", result_url),
        ("authemail", email),
    ]
    if phone and method:
        fields += [("phone", phone), ("method", method)]
        url = f"{settings.PAYNOW_BASE_URL}/remotetransaction"
    else:
        url = f"{settings.PAYNOW_BASE_URL}/initiatetransaction"
    fields.append(("status", "Message"))
    return _send(url, fields, conf.key)


def poll(currency: str, poll_url: str) -> dict[str, str]:
    conf = integration(currency)
    if not poll_url.startswith(settings.PAYNOW_BASE_URL.rsplit("/interface", 1)[0]):
        raise PaynowError("Unexpected poll URL.")  # never call a URL an attacker supplied
    try:
        body = _transport(poll_url, {})
    except OSError as exc:
        raise PaynowError("Paynow could not be reached.") from exc
    reply = parse(body)
    if not verify(reply, conf.key):
        raise PaynowError("Paynow's status could not be verified.")
    return {k.lower(): v for k, v in reply}


def local_msisdn(e164: str) -> str:
    """Paynow expects Zimbabwean mobile numbers as 07XXXXXXXX."""
    import phonenumbers

    try:
        parsed = phonenumbers.parse(e164, "ZW")
    except phonenumbers.NumberParseException as exc:
        raise DomainError(
            "validation_error", "Enter a valid mobile number.", details={"phone": ["Invalid."]}
        ) from exc
    if parsed.country_code != 263 or not phonenumbers.is_valid_number(parsed):
        raise DomainError(
            "validation_error",
            "Enter a Zimbabwean mobile number for EcoCash or OneMoney.",
            details={"phone": ["Invalid."]},
        )
    return "0" + str(parsed.national_number)


def sanitise(data: dict[str, Any]) -> dict[str, Any]:
    """What we keep from provider messages (never card data; Paynow never sends it anyway)."""
    keep = ("status", "reference", "paynowreference", "amount", "pollurl", "browserurl", "error")
    return {k: v for k, v in data.items() if k in keep}

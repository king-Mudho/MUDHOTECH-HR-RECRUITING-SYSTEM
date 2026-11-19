"""Adapter base (P15-T01).

Adapters talk to one external provider. In **sandbox** mode (``INTEGRATIONS_SANDBOX``, on by
default outside production, or per connection) no network call is made: requests are recorded in
``SANDBOX_OUTBOX`` and answered with plausible fake responses, so every flow can be exercised and
tested without provider accounts (Phase 15 STOP condition: real accounts are set up by the owner).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

SANDBOX_OUTBOX: list[dict[str, Any]] = []


class IntegrationError(Exception):
    """A provider call failed; recorded on the connection, never raised into core code."""


class BaseAdapter:
    timeout = 15

    def __init__(self, connection: Any, credentials: dict[str, Any]) -> None:
        self.connection = connection
        self.credentials = credentials
        self.config = dict(connection.config or {})

    @property
    def sandbox(self) -> bool:
        return bool(self.connection.sandbox or settings.INTEGRATIONS_SANDBOX)

    def request(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        sandbox_reply: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.sandbox:
            SANDBOX_OUTBOX.append(
                {"provider": self.connection.provider, "method": method, "url": url, "body": body}
            )
            return dict(sandbox_reply or {"ok": True})
        if not url.startswith("https://"):
            raise IntegrationError("Provider URLs must use HTTPS.")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(  # noqa: S310 - https only (checked above)
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310  # nosec B310 - https only
                raw = resp.read().decode() or "{}"
        except urllib.error.HTTPError as exc:
            raise IntegrationError(f"{self.connection.provider}: HTTP {exc.code}") from exc
        except OSError as exc:
            raise IntegrationError(f"{self.connection.provider}: unreachable") from exc
        try:
            return dict(json.loads(raw))
        except ValueError:
            return {"raw": raw[:500]}

    def ping(self) -> dict[str, Any]:
        """Cheap authenticated call used by the 'test connection' button."""
        return {"ok": True}

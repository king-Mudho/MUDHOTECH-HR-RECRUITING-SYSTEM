"""Messaging adapters (P15-T04, ADR-032): a generic HTTP SMS aggregator adapter and the WhatsApp
Business Cloud API (approved templates only).

The SMS adapter speaks a small JSON protocol (``POST {base}/messages`` with a bearer API key) that
local Zimbabwean aggregators expose or that a thin proxy can provide; the base URL is a setting so
the owner can pick the vendor (decision D-14). WhatsApp messages outside a customer-initiated
session must use pre-approved templates, so only templates are sent.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .base import BaseAdapter, IntegrationError


class SmsAggregatorAdapter(BaseAdapter):
    def send(self, to: str, text: str, reference: str) -> dict[str, Any]:
        base = settings.SMS_AGGREGATOR_BASE_URL.rstrip("/")
        if not base and not self.sandbox:
            raise IntegrationError("sms: aggregator URL not configured")
        reply = self.request(
            "POST",
            f"{base}/messages",
            body={
                "to": to,
                "message": text[:612],  # 4 SMS segments at most
                "sender_id": self.config.get("sender_id", "MHRS"),
                "reference": reference,
                "callback_url": (f"{settings.CALLBACK_BASE_URL}/api/v1/integrations/sms/receipt/"),
            },
            headers={"Authorization": f"Bearer {self.credentials.get('api_key', '')}"},
            sandbox_reply={"id": f"sms-{reference}", "status": "queued", "cost": "0.03"},
        )
        return reply

    def ping(self) -> dict[str, Any]:
        base = settings.SMS_AGGREGATOR_BASE_URL.rstrip("/")
        return self.request(
            "GET",
            f"{base}/balance",
            headers={"Authorization": f"Bearer {self.credentials.get('api_key', '')}"},
            sandbox_reply={"ok": True, "balance": "100.00"},
        )


class WhatsAppCloudAdapter(BaseAdapter):
    graph = "https://graph.facebook.com/v20.0"

    def send_template(
        self, to: str, template: str, language: str, parameters: list[str], reference: str
    ) -> dict[str, Any]:
        phone_id = self.config.get("phone_number_id", "")
        return self.request(
            "POST",
            f"{self.graph}/{phone_id}/messages",
            body={
                "messaging_product": "whatsapp",
                "to": to.lstrip("+"),
                "type": "template",
                "biz_opaque_callback_data": reference,
                "template": {
                    "name": template,
                    "language": {"code": language},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": p[:200]} for p in parameters],
                        }
                    ],
                },
            },
            headers={"Authorization": f"Bearer {self.credentials.get('access_token', '')}"},
            sandbox_reply={"messages": [{"id": f"wamid.{reference}"}]},
        )

    def ping(self) -> dict[str, Any]:
        phone_id = self.config.get("phone_number_id", "")
        return self.request(
            "GET",
            f"{self.graph}/{phone_id}",
            headers={"Authorization": f"Bearer {self.credentials.get('access_token', '')}"},
            sandbox_reply={"id": phone_id or "sandbox", "verified_name": "Sandbox"},
        )

"""allauth account adapter: outbox-backed email + progressive lockout."""

from __future__ import annotations

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest

from . import lockout


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix: str, email: str, context: dict[str, Any]) -> None:
        """Render now (needs the request), deliver later through the outbox."""
        from allauth.core import context as allauth_context

        from apps.core.email import queue_email

        request = allauth_context.request
        ctx = {"request": request, "email": email, "app_name": "MUDHOTECH HR RECRUITING SYSTEM"}
        ctx.update(context)
        msg = self.render_mail(template_prefix, email, ctx)
        html = None
        for content, mimetype in getattr(msg, "alternatives", []) or []:
            if mimetype == "text/html":
                html = str(content)
        queue_email(
            list(msg.to),
            str(msg.subject),
            str(msg.body),
            html,
            category=template_prefix.rsplit("/", 1)[-1],
        )

    def pre_authenticate(self, request: HttpRequest, **credentials: Any) -> None:
        super().pre_authenticate(request, **credentials)
        if lockout.is_locked(credentials.get("email") or credentials.get("username") or ""):
            # Same generic error as rate limiting - never reveal whether the account exists.
            raise self.validation_error("too_many_login_attempts")

    def authentication_failed(self, request: HttpRequest, **credentials: Any) -> None:
        lockout.register_failure(credentials.get("email") or credentials.get("username") or "")

    def login(self, request: HttpRequest, user: Any) -> None:
        lockout.register_success(user.email)
        super().login(request, user)

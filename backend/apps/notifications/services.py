"""Template management and rendering (P05-T01). Delivery lives in ``delivery.py`` (P05-T03)."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models import Max, Q, QuerySet

from apps.audit import services as audit
from apps.core.exceptions import DomainError, NotFoundError

from . import registry
from .models import Channel, NotificationTemplate
from .renderer import Rendered, TemplateRenderError, TemplateValidationError, render, validate

logger = logging.getLogger("mhrs.notifications")

BRAND = "MUDHOTECH HR RECRUITING SYSTEM"


def _org_id(org: Any) -> Any:
    return getattr(org, "pk", org)


def visible_templates(org: Any) -> QuerySet[NotificationTemplate]:
    """Platform defaults plus this organisation's own versions (never another org's)."""
    return NotificationTemplate.objects.filter(
        Q(organisation__isnull=True) | Q(organisation=_org_id(org))
    )


def platform_default(
    key: str, channel: str = Channel.EMAIL, locale: str = "en"
) -> NotificationTemplate | None:
    return NotificationTemplate.objects.filter(
        organisation__isnull=True, key=key, channel=channel, locale=locale, active=True
    ).first()


def effective_template(
    org: Any, key: str, channel: str = Channel.EMAIL, locale: str = "en"
) -> NotificationTemplate | None:
    """The organisation's active override, else the active platform default."""
    if org is not None:
        own = NotificationTemplate.objects.filter(
            organisation=_org_id(org), key=key, channel=channel, locale=locale, active=True
        ).first()
        if own is not None:
            return own
    return platform_default(key, channel, locale)


def _validation_error(exc: TemplateValidationError) -> DomainError:
    return DomainError(
        "validation_error", "Please fix the template.", status_code=400, details=exc.errors
    )


@transaction.atomic
def save_template(
    org: Any,
    *,
    actor: Any,
    key: str,
    subject: str,
    body_md: str,
    channel: str = Channel.EMAIL,
    locale: str = "en",
) -> NotificationTemplate:
    """Create the next version of an organisation's template (``org`` None = platform default)."""
    try:
        kind = registry.get(key)
    except KeyError:
        raise DomainError(
            "validation_error",
            "Unknown notification.",
            status_code=400,
            details={"key": ["Unknown."]},
        ) from None
    if channel == Channel.EMAIL and not subject.strip():
        raise DomainError(
            "validation_error",
            "Please fix the template.",
            details={"subject": ["Required for email."]},
        )
    try:
        used = validate(subject, body_md, kind.allowed)
    except TemplateValidationError as exc:
        raise _validation_error(exc) from None
    org_id = _org_id(org)
    current = NotificationTemplate.objects.select_for_update().filter(
        organisation=org_id, key=key, channel=channel, locale=locale
    )
    latest = current.aggregate(v=Max("version"))["v"] or 0
    before = current.filter(active=True).first()
    current.filter(active=True).update(active=False)
    template = NotificationTemplate.objects.create(
        organisation_id=org_id,
        key=key,
        channel=channel,
        locale=locale,
        subject=subject.strip(),
        body_md=body_md,
        variables=used,
        version=latest + 1,
        active=True,
        created_by=actor,
    )
    audit.record(
        actor=actor,
        action="notification_template.saved",
        target=template,
        organisation=org_id,
        before={"version": before.version} if before else None,
        after={"key": key, "channel": channel, "version": template.version},
    )
    return template


@transaction.atomic
def revert_to_default(
    org: Any, *, actor: Any, key: str, channel: str = Channel.EMAIL, locale: str = "en"
) -> None:
    updated = NotificationTemplate.objects.filter(
        organisation=_org_id(org), key=key, channel=channel, locale=locale, active=True
    ).update(active=False)
    if updated:
        audit.record(
            actor=actor,
            action="notification_template.reverted",
            target=("notifications.notificationtemplate", key),
            organisation=_org_id(org),
            after={"key": key, "channel": channel},
        )


def render_template(template: NotificationTemplate, context: dict[str, Any]) -> Rendered:
    return render(template.subject, template.body_md, context, brand=BRAND)


def render_for(
    org: Any, key: str, context: dict[str, Any], *, channel: str = Channel.EMAIL, locale: str = "en"
) -> tuple[Rendered, NotificationTemplate]:
    """Render the effective template; if an organisation's override cannot render (a value it
    needs is missing), fall back to the platform default (EC-NOT-05)."""
    template = effective_template(org, key, channel, locale)
    if template is None:
        raise NotFoundError(message=f"No template for {key}/{channel}/{locale}.")
    try:
        return render_template(template, context), template
    except TemplateRenderError:
        default = platform_default(key, channel, locale)
        if default is None or default.pk == template.pk:
            raise
        logger.warning(
            "notification_template_fallback",
            extra={"key": key, "template_id": str(template.pk)},
        )
        return render_template(default, context), default


def preview(template: NotificationTemplate, overrides: dict[str, Any] | None = None) -> Rendered:
    context = registry.sample_context(template.key)
    context.update({k: str(v)[:500] for k, v in (overrides or {}).items() if k in context})
    try:
        return render_template(template, context)
    except TemplateRenderError as exc:  # pragma: no cover - samples cover every allowed variable
        raise DomainError("validation_error", str(exc), status_code=400) from None

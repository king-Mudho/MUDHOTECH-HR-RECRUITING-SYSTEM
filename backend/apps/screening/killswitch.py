"""AI kill-switch (P09-T11, docs/runbooks/disable-ai.md).

AI screening runs only while BOTH switches allow it:

* the platform flag ``ai.screening`` (``FeatureFlag``; enabled unless a row says otherwise) - a
  global row switches AI off for every organisation, an organisation row for one tenant;
* the organisation's own ``OrganisationPolicy.ai_enabled``.

While AI is off, applications are never evaluated: they move to ``under_review`` in the
``manual_review_requested`` band (no score, no band hints, no AI text), and the LLM summary and AI
criteria suggestions are unavailable. Switching AI back on does not re-evaluate anything by
itself; HR starts a screening run when they want AI assistance again.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import flags
from apps.core.models import FeatureFlag

FLAG = "ai.screening"


def platform_enabled() -> bool:
    return flags.is_enabled(FLAG, None, default=True)


def ai_allowed(organisation: Any) -> bool:
    """True only when the platform, the organisation override and the org policy all allow AI."""
    from apps.organisations.models import OrganisationPolicy

    org_id = getattr(organisation, "pk", organisation)
    if not flags.is_enabled(FLAG, org_id, default=True):
        return False
    policy = getattr(organisation, "policy", None)
    if policy is None or not isinstance(policy, OrganisationPolicy):
        policy = OrganisationPolicy.objects.filter(organisation_id=org_id).first()
    return policy is None or bool(policy.ai_enabled)


def set_platform(enabled: bool, *, actor: Any, reason: str) -> bool:
    with transaction.atomic():
        before = platform_enabled()
        FeatureFlag.objects.update_or_create(
            key=FLAG, organisation_id=None, defaults={"enabled": enabled}
        )
        audit.record(
            action="ai.kill_switch",
            actor=actor,
            target=("core.featureflag", FLAG),
            organisation=None,
            before={"enabled": before},
            after={"enabled": enabled, "scope": "platform"},
            reason=reason[:500],
        )
    flags.invalidate(FLAG)
    return enabled


def set_for_organisation(
    organisation: Any, enabled: bool | None, *, actor: Any, reason: str
) -> None:
    """Platform override for one tenant; ``None`` removes the override (inherit the platform)."""
    org_id = getattr(organisation, "pk", organisation)
    with transaction.atomic():
        if enabled is None:
            FeatureFlag.objects.filter(key=FLAG, organisation_id=org_id).delete()
        else:
            FeatureFlag.objects.update_or_create(
                key=FLAG, organisation_id=org_id, defaults={"enabled": enabled}
            )
        audit.record(
            action="ai.kill_switch",
            actor=actor,
            target=("core.featureflag", FLAG),
            organisation=org_id,
            after={"enabled": enabled, "scope": "organisation"},
            reason=reason[:500],
        )
    flags.invalidate(FLAG)


def disabled_organisations() -> list[str]:
    return [
        str(o)
        for o in FeatureFlag.objects.filter(key=FLAG, enabled=False)
        .exclude(organisation__isnull=True)
        .values_list("organisation_id", flat=True)
    ]

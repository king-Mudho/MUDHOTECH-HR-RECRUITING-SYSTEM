"""Scorecards (docs/01 M16, P12-T03).

* A panelist fills a draft (1-5 per criterion with evidence notes, overall 1-5, recommendation) and
  submits it. Submitted scorecards are final: a correction is a note to HR, not an edit.
* **Independent assessment (EC-INT-04):** a panelist sees only their own scorecard until they submit
  it; afterwards they see the others' submitted ones. Nobody ever sees another person's draft.
* HR (``interviews.feedback``) sees every submitted scorecard and the consolidated view: per-
  criterion spread, overall average, recommendation tally and who has not submitted yet - for people
  to discuss, never an automatic decision.
* The template is frozen on the first submission so every scorecard of an interview rates the same
  criteria.
"""

from __future__ import annotations

import json
from statistics import mean
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import time as mhrs_time
from apps.core.exceptions import DomainError, PermissionDeniedError
from apps.organisations import rbac
from apps.organisations.models import Membership

from .models import (
    Interview,
    InterviewPanelist,
    InterviewStatus,
    Recommendation,
    Scorecard,
)

RATABLE = (InterviewStatus.SCHEDULED, InterviewStatus.COMPLETED)
NOTE_LIMIT = 2000


def _panelist(interview: Interview, membership: Membership) -> InterviewPanelist:
    panelist = (
        InterviewPanelist.objects.for_org(interview.organisation_id)
        .filter(interview=interview, membership=membership)
        .first()
    )
    if panelist is None:
        raise PermissionDeniedError(message="Only panel members of this interview can rate it.")
    return panelist


def draft_for(interview: Interview, membership: Membership) -> Scorecard:
    """The panelist's own scorecard (created on first use)."""
    panelist = _panelist(interview, membership)
    template = interview.scorecard_template
    if template is None:
        raise DomainError(
            "no_scorecard_template", "Add a scorecard to this interview before rating it.", 409
        )
    card, _ = Scorecard.objects.for_org(interview.organisation_id).get_or_create(
        interview=interview,
        panelist=panelist,
        defaults={"organisation_id": interview.organisation_id, "template": template},
    )
    return card


def _clean(card: Scorecard, data: dict[str, Any]) -> dict[str, Any]:
    keys = set(card.template.keys)
    errors: dict[str, list[str]] = {}
    scores = data.get("scores", card.scores) or {}
    if not isinstance(scores, dict):
        errors["scores"] = ["Expected an object of criterion: rating."]
        scores = {}
    clean_scores: dict[str, int] = {}
    for key, value in scores.items():
        if key not in keys:
            errors.setdefault("scores", []).append(f"Unknown criterion '{key}'.")
        elif value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                errors.setdefault("scores", []).append(
                    f"'{key}' must be a whole number from 1 to 5."
                )
            else:
                clean_scores[key] = value
    notes_in = data.get("criterion_notes")
    if notes_in is None:
        crit_notes = json.loads(card.criterion_notes) if card.criterion_notes else {}
    elif isinstance(notes_in, dict):
        crit_notes = {}
        for key, text in notes_in.items():
            if key not in keys:
                errors.setdefault("criterion_notes", []).append(f"Unknown criterion '{key}'.")
            elif text:
                crit_notes[key] = str(text).strip()[:NOTE_LIMIT]
    else:
        errors["criterion_notes"] = ["Expected an object of criterion: note."]
        crit_notes = {}
    overall = data.get("overall", card.overall)
    if overall is not None and (
        isinstance(overall, bool) or not isinstance(overall, int) or not 1 <= overall <= 5
    ):
        errors["overall"] = ["A whole number from 1 to 5."]
    recommendation = data.get("recommendation", card.recommendation) or ""
    if recommendation and recommendation not in Recommendation.values:
        errors["recommendation"] = ["Unknown recommendation."]
    if errors:
        raise DomainError("validation_error", "Please check the scorecard.", 422, errors)
    return {
        "scores": clean_scores,
        "criterion_notes": json.dumps(crit_notes, ensure_ascii=False) if crit_notes else "",
        "overall": overall,
        "recommendation": recommendation,
        "notes": str(data.get("notes", card.notes) or "").strip()[: NOTE_LIMIT * 2],
    }


def save_draft(interview: Interview, membership: Membership, data: dict[str, Any]) -> Scorecard:
    with transaction.atomic():
        card = draft_for(interview, membership)
        card = Scorecard.objects.for_org(card.organisation_id).select_for_update().get(pk=card.pk)
        if card.submitted_at:
            raise DomainError("scorecard_submitted", "This scorecard was already submitted.", 409)
        for name, value in _clean(card, data).items():
            setattr(card, name, value)
        card.save()
    return card


def submit(
    interview: Interview, membership: Membership, data: dict[str, Any] | None = None
) -> Scorecard:
    with transaction.atomic():
        iv = (
            Interview.objects.for_org(interview.organisation_id)
            .select_for_update()
            .get(pk=interview.pk)
        )
        card = draft_for(iv, membership)
        card = Scorecard.objects.for_org(card.organisation_id).select_for_update().get(pk=card.pk)
        if card.submitted_at:
            raise DomainError("scorecard_submitted", "This scorecard was already submitted.", 409)
        if iv.status not in RATABLE or iv.starts_at is None or iv.starts_at > mhrs_time.now():
            raise DomainError(
                "interview_not_held",
                "A scorecard can be submitted once the interview has started.",
                409,
            )
        values = _clean(card, data or {})
        missing = [k for k in card.template.keys if k not in values["scores"]]
        errors: dict[str, list[str]] = {}
        if missing:
            errors["scores"] = [f"Rate every criterion (missing: {', '.join(missing)})."]
        if values["overall"] is None:
            errors["overall"] = ["Give an overall rating."]
        if not values["recommendation"]:
            errors["recommendation"] = ["Choose a recommendation."]
        if errors:
            raise DomainError("validation_error", "The scorecard is not complete.", 422, errors)
        for name, value in values.items():
            setattr(card, name, value)
        card.submitted_at = mhrs_time.now()
        card.save()
        template = card.template
        if template.locked_at is None:
            template.locked_at = card.submitted_at
            template.save(update_fields=["locked_at", "updated_at"])
        audit.record(
            actor=membership.user,
            action="interviews.scorecard_submitted",
            target=card,
            organisation=iv.organisation_id,
            after={
                "interview_id": str(iv.pk),
                "overall": card.overall,
                "recommendation": card.recommendation,
            },
        )
    return card


# --- reading --------------------------------------------------------------------------------------
def can_see_all_feedback(membership: Membership) -> bool:
    return rbac.can(membership.role, "interviews.feedback")


def visible_scorecards(interview: Interview, membership: Membership) -> list[Scorecard]:
    """EC-INT-04: own card (draft or submitted) until submitted; then the others' submitted cards.
    HR with ``interviews.feedback`` sees every submitted card (plus its own draft if on the panel)
    """
    cards = (
        Scorecard.objects.for_org(interview.organisation_id)
        .filter(interview=interview)
        .select_related("panelist__membership__user", "template")
        .order_by("submitted_at", "created_at")
    )
    own = next((c for c in cards if c.panelist.membership_id == membership.pk), None)
    is_panelist = (
        InterviewPanelist.objects.for_org(interview.organisation_id)
        .filter(interview=interview, membership=membership)
        .exists()
    )
    if can_see_all_feedback(membership) and not (
        is_panelist and (own is None or not own.submitted_at)
    ):
        others = [c for c in cards if c.submitted_at and c is not own]
        return ([own] if own else []) + others
    if not is_panelist:
        raise PermissionDeniedError(message="You are not on this interview's panel.")
    if own is None or not own.submitted_at:
        return [own] if own else []
    return [own] + [c for c in cards if c.submitted_at and c is not own]


def consolidated(interview: Interview, membership: Membership) -> dict[str, Any]:
    """HR's summary of one interview's submitted scorecards (discussion aid, not a decision)."""
    if not can_see_all_feedback(membership):
        raise PermissionDeniedError(message="You can't see the consolidated feedback.")
    template = interview.scorecard_template
    cards = list(
        Scorecard.objects.for_org(interview.organisation_id)
        .filter(interview=interview, submitted_at__isnull=False)
        .select_related("panelist__membership__user")
    )
    panel = list(
        InterviewPanelist.objects.for_org(interview.organisation_id)
        .filter(interview=interview)
        .select_related("membership__user")
    )
    submitted = {c.panelist_id for c in cards}
    criteria = []
    for c in template.criteria if template else []:
        values = [card.scores[c["key"]] for card in cards if c["key"] in card.scores]
        criteria.append(
            {
                "key": c["key"],
                "title": c["title"],
                "count": len(values),
                "average": round(mean(values), 2) if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                # a spread of 3+ points on a 1-5 scale is worth discussing before deciding
                "disagreement": bool(values) and max(values) - min(values) >= 3,
            }
        )
    tally = dict.fromkeys(Recommendation.values, 0)
    for card in cards:
        tally[card.recommendation] += 1
    overall = [card.overall for card in cards if card.overall]
    return {
        "interview_id": str(interview.pk),
        "submitted": len(cards),
        "panel_size": len(panel),
        "outstanding": [
            {
                "membership_id": str(p.membership_id),
                "name": p.membership.user.full_name or p.membership.user.email,
            }
            for p in panel
            if p.pk not in submitted
        ],
        "criteria": criteria,
        "overall_average": round(mean(overall), 2) if overall else None,
        "recommendations": tally,
    }

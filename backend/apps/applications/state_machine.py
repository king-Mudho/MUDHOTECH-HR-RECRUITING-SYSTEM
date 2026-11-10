"""Application state machine (SRS §3.3) - the single source of truth for status changes.

Each allowed ``(from, to)`` pair names who may perform it:

* ``candidate`` - the applicant (submit, withdraw);
* ``staff`` - an authenticated organisation member (always a human; a reason is recorded);
* ``system`` - background processing (screening pipeline, deadline jobs).

Consequential outcomes (``shortlisted``, ``not_selected``, ``offer``, ``hired``) and every reopen
of a terminal application are **human-only with a mandatory reason** (principle 1). An AI
recommendation is never a status.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import TERMINAL_STATUSES, Status

S = Status
CANDIDATE, STAFF, SYSTEM = "candidate", "staff", "system"


@dataclass(frozen=True)
class Rule:
    actors: frozenset[str]
    reason_required: bool = False


def _r(*actors: str, reason: bool = False) -> Rule:
    return Rule(frozenset(actors), reason)


HUMAN_DECISION = _r(STAFF, reason=True)

TRANSITIONS: dict[tuple[str, str], Rule] = {
    (S.DRAFT, S.SUBMITTED): _r(CANDIDATE, STAFF),  # staff: assisted application (EC-APP-17)
    (S.DRAFT, S.ABANDONED): _r(SYSTEM, CANDIDATE),
    (S.SUBMITTED, S.PROCESSING): _r(SYSTEM),
    (S.SUBMITTED, S.WITHDRAWN): _r(CANDIDATE),
    (S.PROCESSING, S.UNDER_REVIEW): _r(SYSTEM),
    (S.PROCESSING, S.NEEDS_INFORMATION): _r(SYSTEM, STAFF),
    (S.PROCESSING, S.PROCESSING_ERROR): _r(SYSTEM),
    (S.PROCESSING, S.WITHDRAWN): _r(CANDIDATE),
    (S.PROCESSING_ERROR, S.PROCESSING): _r(SYSTEM, STAFF),  # retry
    (S.PROCESSING_ERROR, S.UNDER_REVIEW): _r(STAFF, reason=True),  # manual review
    (S.PROCESSING_ERROR, S.WITHDRAWN): _r(CANDIDATE),
    (S.NEEDS_INFORMATION, S.PROCESSING): _r(SYSTEM, CANDIDATE),  # answer received
    (S.NEEDS_INFORMATION, S.UNDER_REVIEW): _r(STAFF),
    (S.NEEDS_INFORMATION, S.WITHDRAWN): _r(CANDIDATE),
    (S.UNDER_REVIEW, S.SHORTLISTED): HUMAN_DECISION,
    (S.UNDER_REVIEW, S.ON_HOLD): _r(STAFF),
    (S.UNDER_REVIEW, S.NOT_SELECTED): HUMAN_DECISION,
    (S.UNDER_REVIEW, S.NEEDS_INFORMATION): _r(STAFF),
    (S.UNDER_REVIEW, S.WITHDRAWN): _r(CANDIDATE),
    (S.ON_HOLD, S.UNDER_REVIEW): _r(STAFF),
    (S.ON_HOLD, S.SHORTLISTED): HUMAN_DECISION,
    (S.ON_HOLD, S.NOT_SELECTED): HUMAN_DECISION,
    (S.ON_HOLD, S.WITHDRAWN): _r(CANDIDATE),
    (S.SHORTLISTED, S.INTERVIEW): _r(STAFF),
    (S.SHORTLISTED, S.NOT_SELECTED): HUMAN_DECISION,
    (S.SHORTLISTED, S.WITHDRAWN): _r(CANDIDATE),
    (S.INTERVIEW, S.OFFER): HUMAN_DECISION,
    (S.INTERVIEW, S.NOT_SELECTED): HUMAN_DECISION,
    (S.INTERVIEW, S.WITHDRAWN): _r(CANDIDATE),
    (S.OFFER, S.HIRED): HUMAN_DECISION,
    (S.OFFER, S.OFFER_DECLINED): _r(CANDIDATE, STAFF),
    (S.OFFER, S.WITHDRAWN): _r(CANDIDATE),
}
# Authorised reopen of any terminal outcome (with reason) back into review.
for _terminal in TERMINAL_STATUSES:
    TRANSITIONS[(_terminal, S.UNDER_REVIEW)] = HUMAN_DECISION

HUMAN_ONLY_TARGETS = frozenset({S.SHORTLISTED, S.NOT_SELECTED, S.OFFER, S.HIRED})


def rule_for(from_status: str, to_status: str) -> Rule | None:
    return TRANSITIONS.get((from_status, to_status))


def allowed_targets(from_status: str, actor_kind: str | None = None) -> list[str]:
    return sorted(
        to
        for (frm, to), rule in TRANSITIONS.items()
        if frm == from_status and (actor_kind is None or actor_kind in rule.actors)
    )


def is_reopen(from_status: str, to_status: str) -> bool:
    return from_status in TERMINAL_STATUSES and to_status == S.UNDER_REVIEW

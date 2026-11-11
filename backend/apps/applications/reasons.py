"""Platform default decision reasons. Seeded by migration 0006 and re-synced after every
``migrate`` / test-database flush (``post_migrate``), like the notification templates."""

from __future__ import annotations

REASONS: dict[str, list[tuple[str, str]]] = {
    "shortlist": [
        ("meets_essential", "Meets the essential requirements"),
        ("strong_evidence", "Strong evidence of relevant experience"),
        ("clarification_satisfactory", "Clarification answers were satisfactory"),
        ("other", "Other (explained in the note)"),
    ],
    "not_selected": [
        ("essential_not_met", "Essential requirement not evidenced"),
        ("stronger_match_elsewhere", "Other applicants matched the requirements more closely"),
        ("position_filled", "The position has been filled"),
        ("no_response", "No response to a clarification request"),
        ("other", "Other (explained in the note)"),
    ],
    "hold": [
        ("awaiting_information", "Waiting for more information"),
        ("awaiting_budget", "Waiting for budget or approval"),
        ("future_round", "Kept for a later round"),
        ("other", "Other (explained in the note)"),
    ],
    "override": [
        ("decided_in_error", "Earlier decision was made in error"),
        ("new_information", "New information received"),
        ("candidate_request", "Candidate asked for reconsideration"),
        ("other", "Other (explained in the note)"),
    ],
}


def sync_default_reasons() -> int:
    """Create missing platform reasons and refresh labels (idempotent). Returns rows created."""
    from .models import DecisionReason

    created = 0
    for applies_to, items in REASONS.items():
        for code, label in items:
            _, was_created = DecisionReason.objects.update_or_create(
                organisation=None,
                applies_to=applies_to,
                code=code,
                defaults={"label": label, "active": True},
            )
            created += int(was_created)
    return created

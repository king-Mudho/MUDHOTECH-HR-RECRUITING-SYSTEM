"""Notification keys, the variables each template may use, and sample data for previews.

Templates can only reference the variables listed for their key (validated on save). No key
exposes scores, evaluations or other sensitive details (FR-M14-04): emails carry links to the
portal instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COMMON = ("recipient_name", "portal_url", "support_email", "platform_name")


@dataclass(frozen=True)
class NotificationKind:
    key: str
    description: str
    audience: str  # candidate | staff
    variables: tuple[str, ...]
    urgent: bool = False  # urgent ones ignore quiet hours (EC-NOT-09)
    samples: dict[str, str] = field(default_factory=dict)

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset(COMMON) | frozenset(self.variables)


SAMPLES: dict[str, str] = {
    "recipient_name": "Tendai",
    "portal_url": "https://mhrs.example/candidate/dashboard",
    "support_email": "support@mhrs.example",
    "platform_name": "MUDHOTECH HR RECRUITING SYSTEM",
    "organisation_name": "MudhoTech Demo Ltd",
    "job_title": "Software Developer",
    "reference": "MHRS-MUDHOT1A2B-2026-000042",
    "application_url": "https://mhrs.example/candidate/applications/42",
    "document_name": "cv.pdf",
    "reason": "This file didn't pass our security check.",
    "due_date": "15 November 2026",
    "clarification_url": "https://mhrs.example/candidate/applications/42#clarifications",
    "deadline": "30 November 2026, 17:00 (Africa/Harare)",
    "apply_url": "https://mhrs.example/apply/42",
    "invitation_url": "https://mhrs.example/invitations/abc",
    "inviter_name": "Rudo Moyo",
    "role_name": "Recruiter",
    "request_reference": "RR-2026-0007",
    "request_status": "In progress",
    "new_applications": "12",
    "processing_done": "9",
    "dashboard_url": "https://mhrs.example/hr/dashboard",
    "mention_author": "Rudo Moyo",
    "note_url": "https://mhrs.example/hr/applications/42#notes",
    "candidate_name": "Tendai Moyo",
    "sender_name": "MudhoTech Demo Ltd",
    "message_url": "https://mhrs.example/candidate/applications/42#messages",
}

_KINDS = [
    NotificationKind(
        "application_received",
        "Receipt after a candidate submits",
        "candidate",
        ("organisation_name", "job_title", "reference", "application_url"),
        urgent=True,
    ),
    NotificationKind(
        "document_rejected_reupload",
        "A document could not be accepted; ask for a new upload",
        "candidate",
        ("document_name", "reason", "application_url"),
        urgent=True,
    ),
    NotificationKind(
        "clarification_requested",
        "HR asked the candidate for more information",
        "candidate",
        ("organisation_name", "job_title", "due_date", "clarification_url"),
    ),
    NotificationKind(
        "clarification_reminder",
        "Reminder before a clarification is due",
        "candidate",
        ("organisation_name", "job_title", "due_date", "clarification_url"),
    ),
    NotificationKind(
        "application_withdrawn_confirmation",
        "Confirms a withdrawal",
        "candidate",
        ("organisation_name", "job_title", "reference"),
        urgent=True,
    ),
    NotificationKind(
        "draft_deadline_reminder",
        "Unfinished application close to the deadline",
        "candidate",
        ("organisation_name", "job_title", "deadline", "apply_url"),
    ),
    NotificationKind(
        "draft_abandoned",
        "The vacancy closed before the draft was submitted",
        "candidate",
        ("organisation_name", "job_title"),
    ),
    NotificationKind(
        "shortlisted",
        "Candidate shortlisted (after human approval)",
        "candidate",
        ("organisation_name", "job_title", "application_url"),
    ),
    NotificationKind(
        "not_selected",
        "Respectful outcome message (no scores)",
        "candidate",
        ("organisation_name", "job_title"),
    ),
    NotificationKind(
        "recruitment_paused",
        "The vacancy was paused",
        "candidate",
        ("organisation_name", "job_title"),
    ),
    NotificationKind(
        "invitation_staff",
        "Invitation to join an organisation",
        "staff",
        ("organisation_name", "inviter_name", "role_name", "invitation_url"),
        urgent=True,
    ),
    NotificationKind(
        "rights_request_update",
        "Update on a data-rights request",
        "candidate",
        ("organisation_name", "request_reference", "request_status"),
        urgent=True,
    ),
    NotificationKind(
        "recruiter_digest",
        "New applications and processing results",
        "staff",
        ("organisation_name", "job_title", "new_applications", "processing_done", "dashboard_url"),
    ),
    NotificationKind(
        "note_mention",
        "A colleague mentioned you in a note",
        "staff",
        ("mention_author", "job_title", "note_url"),
        urgent=True,
    ),
    NotificationKind(
        "clarification_answered",
        "A candidate answered a clarification request",
        "staff",
        ("candidate_name", "job_title", "reference", "application_url"),
        urgent=True,
    ),
    NotificationKind(
        "clarification_expired",
        "A clarification request passed its due date without an answer",
        "staff",
        ("candidate_name", "job_title", "reference", "application_url"),
        urgent=True,
    ),
    NotificationKind(
        "new_message",
        "A new message in an application's conversation",
        "candidate",
        ("sender_name", "job_title", "message_url"),
        urgent=True,
    ),
]

KINDS: dict[str, NotificationKind] = {k.key: k for k in _KINDS}


def get(key: str) -> NotificationKind:
    try:
        return KINDS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown notification key: {key}") from exc


def sample_context(key: str) -> dict[str, str]:
    kind = get(key)
    return {name: SAMPLES.get(name, name.replace("_", " ")) for name in sorted(kind.allowed)}

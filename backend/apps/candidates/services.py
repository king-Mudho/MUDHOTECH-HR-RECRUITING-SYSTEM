"""Candidate profile services: get-or-create, locked updates, section CRUD and completeness."""

from __future__ import annotations

from typing import Any

import phonenumbers
from django.db import transaction

from apps.core.exceptions import DomainError, StaleVersionError

from .models import CandidateProfile

PROFILE_FIELDS = (
    "preferred_name",
    "headline",
    "summary",
    "city",
    "country",
    "phone_e164",
    "links",
    "availability",
    "notice_period_days",
    "open_to_relocation",
)
LINK_KEYS = ("linkedin", "github", "portfolio", "other")

# Completeness weights (sum 100). Shown to candidates as guidance only; never used in screening.
WEIGHTS = {
    "headline": 10,
    "summary": 10,
    "location": 5,
    "phone": 10,
    "experience": 20,
    "education": 15,
    "skills": 15,
    "languages": 5,
    "resume": 10,
}


def get_or_create_profile(user: Any) -> CandidateProfile:
    profile, _ = CandidateProfile.objects.get_or_create(user=user)
    return profile


def normalise_phone(value: str, region: str = "ZW") -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = phonenumbers.parse(value, region or "ZW")
    except phonenumbers.NumberParseException as exc:
        raise DomainError(
            "validation_error", "Enter a valid phone number.", details={"phone_e164": ["Invalid."]}
        ) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise DomainError(
            "validation_error", "Enter a valid phone number.", details={"phone_e164": ["Invalid."]}
        )
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _clean_links(links: Any) -> dict[str, str]:
    if not isinstance(links, dict):
        raise DomainError("validation_error", "Invalid links.", details={"links": ["Invalid."]})
    out: dict[str, str] = {}
    for key in LINK_KEYS:
        url = str(links.get(key) or "").strip()
        if not url:
            continue
        if not url.lower().startswith(("https://", "http://")) or len(url) > 300:
            raise DomainError(
                "validation_error",
                "Links must start with http:// or https://.",
                details={"links": [f"{key}: invalid address."]},
            )
        out[key] = url
    return out


@transaction.atomic
def update_profile(
    user: Any, data: dict[str, Any], *, lock_version: int | None = None
) -> CandidateProfile:
    profile = get_or_create_profile(user)
    profile = CandidateProfile.objects.select_for_update().get(pk=profile.pk)
    if lock_version is not None and lock_version != profile.lock_version:
        raise StaleVersionError(details={"current_lock_version": profile.lock_version})
    for name in PROFILE_FIELDS:
        if name not in data:
            continue
        value = data[name]
        if name == "phone_e164":
            value = normalise_phone(value, data.get("country") or profile.country)
        elif name == "links":
            value = _clean_links(value)
        elif name == "country":
            value = str(value or "ZW").upper()[:2]
        setattr(profile, name, value)
    profile.lock_version += 1
    profile.save()
    return recompute_completeness(profile)


def completeness(profile: CandidateProfile) -> tuple[int, list[str]]:
    """Score 0-100 plus the list of missing sections (drives the profile checklist UI)."""
    checks = {
        "headline": bool(profile.headline.strip()),
        "summary": len(profile.summary.strip()) >= 40,
        "location": bool(profile.city.strip()),
        "phone": bool(profile.phone_e164),
        "experience": profile.experiences.exists(),
        "education": profile.educations.exists(),
        "skills": profile.skills.count() >= 3,
        "languages": profile.languages.exists(),
        "resume": bool(getattr(profile, "default_resume_id", None)),
    }
    score = sum(WEIGHTS[k] for k, ok in checks.items() if ok)
    return score, [k for k, ok in checks.items() if not ok]


def recompute_completeness(profile: CandidateProfile) -> CandidateProfile:
    score, _ = completeness(profile)
    if score != profile.profile_completeness:
        CandidateProfile.objects.filter(pk=profile.pk).update(profile_completeness=score)
        profile.profile_completeness = score
    return profile


def profile_snapshot(user: Any, contact: dict[str, Any] | None = None) -> dict[str, Any]:
    """Frozen copy of the candidate's profile for an application (shared with the employer at
    submit). Never contains protected attributes - the profile has none (FR-M06-02)."""
    profile = get_or_create_profile(user)
    contact = contact or {}

    def d(value: Any) -> str | None:
        return value.isoformat() if value else None

    return {
        "first_name": contact.get("first_name") or user.first_name,
        "last_name": contact.get("last_name") or user.last_name,
        "preferred_name": contact.get("preferred_name") or profile.preferred_name,
        "email": user.email,
        "phone": contact.get("phone") or profile.phone_e164,
        "city": contact.get("city") or profile.city,
        "country": profile.country,
        "headline": profile.headline,
        "summary": profile.summary,
        "links": profile.links,
        "availability": profile.availability,
        "notice_period_days": profile.notice_period_days,
        "open_to_relocation": profile.open_to_relocation,
        "experiences": [
            {
                "employer": e.employer,
                "title": e.title,
                "location": e.location,
                "start_date": d(e.start_date),
                "end_date": d(e.end_date),
                "is_current": e.is_current,
                "description": e.description,
                "source": e.source,
            }
            for e in profile.experiences.all()
        ],
        "educations": [
            {
                "institution": e.institution,
                "qualification_text": e.qualification_text,
                "qualification_level_id": str(e.qualification_level_id)
                if e.qualification_level_id
                else None,
                "field": e.field,
                "start_date": d(e.start_date),
                "end_date": d(e.end_date),
                "grade": e.grade,
            }
            for e in profile.educations.all()
        ],
        "certifications": [
            {"name": c.name, "issued_at": d(c.issued_at), "expires_at": d(c.expires_at)}
            for c in profile.certifications.all()
        ],
        "skills": [
            {
                "name": s.raw_name,
                "skill_id": str(s.skill_id) if s.skill_id else None,
                "proficiency": s.proficiency,
                "years": str(s.years) if s.years is not None else None,
            }
            for s in profile.skills.all()
        ],
        "languages": [
            {"language": lang.language, "proficiency": lang.proficiency}
            for lang in profile.languages.all()
        ],
        "profile_updated_at": profile.updated_at.isoformat(),
    }

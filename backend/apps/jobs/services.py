"""Vacancy services (P03-T05): drafting, readiness lint, approval and the publish lifecycle.

Lifecycle (SRS §3.2): ``draft -> in_review -> approved -> scheduled|published -> paused <->
published -> closed -> archived``. Content lives on ``JobVersion``; approval freezes the version
(criteria, rubric, questionnaire and a snapshot of the advert). Editing a live vacancy goes through
``new_version`` -> submit -> approve, which swaps ``published_version`` (EC-JOB-06).

Every transition writes a ``JobEvent`` + audit event inside one transaction; ``job.published`` and
``job.closed`` (and a few other lifecycle events) go through the outbox.
"""

from __future__ import annotations

import zoneinfo
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import outbox
from apps.core.exceptions import (
    ConflictError,
    DomainError,
    InvalidTransitionError,
    PermissionDeniedError,
    StaleVersionError,
)
from apps.core.sanitize import sanitize_html
from apps.core.time import now
from apps.organisations import rbac
from apps.organisations.models import Membership, Organisation, OrganisationPolicy
from apps.organisations.selectors import active_membership
from apps.organisations.services import OrgUnverifiedError, assert_can_publish
from apps.questionnaires.models import Questionnaire
from apps.questionnaires.services import blocking_questions, flags_for, replace_questions
from apps.questionnaires.validation import validate_questions

from .models import (
    CriterionType,
    Importance,
    Job,
    JobApproval,
    JobAssignment,
    JobCriterion,
    JobEvent,
    JobStatus,
    JobVersion,
    Rubric,
    RubricCategory,
    RubricStatus,
    VersionStatus,
    WorkplaceType,
)
from .search import unique_job_slug, update_search_vector

S = JobStatus
LIVE = {S.PUBLISHED, S.PAUSED, S.SCHEDULED}
MIN_REASON = 5
SHORT_DEADLINE = timedelta(hours=24)

HEADER_FIELDS = (
    "title",
    "reference_code",
    "visibility",
    "workplace_type",
    "employment_type",
    "seniority",
    "openings",
    "closes_at",
    "timezone",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "salary_disclosed",
    "start_date",
)
VERSION_TEXT_FIELDS = ("summary", "change_note")
VERSION_HTML_FIELDS = ("responsibilities_html", "requirements_html", "benefits_html")
REQUIRED_DOCUMENT_TYPES = {
    "cv",
    "cover_letter",
    "certificates",
    "transcripts",
    "id_document",
    "professional_registration",
    "portfolio",
    "references",
}


# --------------------------------------------------------------------------------------------
# helpers


def _require(actor: Any, org: Organisation, action: str) -> Membership:
    membership = active_membership(actor, org.pk)
    if membership is None or not rbac.can(membership.role, action):
        raise PermissionDeniedError()
    if org.is_read_only:
        from apps.core.exceptions import OrgSuspendedError

        raise OrgSuspendedError()
    return membership


def _lock(job: Job) -> Job:
    return Job.objects.for_org(job.organisation_id).select_for_update().get(pk=job.pk)


def _check_lock(job: Job, lock_version: int | None) -> None:
    if lock_version is not None and int(lock_version) != job.lock_version:
        raise StaleVersionError(details={"current_lock_version": job.lock_version})


def _bump(job: Job, *fields: str) -> None:
    job.lock_version += 1
    job.save(update_fields=["lock_version", "updated_at", *fields])


def _reason(reason: str | None, *, required: bool = True) -> str:
    text = (reason or "").strip()
    if required and len(text) < MIN_REASON:
        raise DomainError(
            "validation_error",
            "Please give a reason.",
            details={"reason": [f"At least {MIN_REASON} characters."]},
        )
    return text


def _event(
    job: Job,
    action: str,
    from_status: str,
    actor: Any,
    reason: str = "",
    *,
    audit_after: dict[str, Any] | None = None,
) -> None:
    version = job.current_version
    JobEvent.objects.create(
        organisation=job.organisation,
        job=job,
        from_status=from_status,
        to_status=job.status,
        action=action,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        reason=reason,
        version_number=version.number if version else None,
    )
    audit.record(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_type=None if getattr(actor, "is_authenticated", False) else "system",
        action=f"job.{action}",
        target=job,
        before={"status": from_status},
        after={"status": job.status, **(audit_after or {})},
        reason=reason,
    )


def _transition(job: Job, allowed_from: set[str], to: str, action: str) -> str:
    if job.status not in allowed_from:
        raise InvalidTransitionError(
            message=f"A {job.get_status_display().lower()} vacancy cannot be {action}.",
            details={"status": job.status, "action": action},
        )
    previous = job.status
    job.status = to
    return previous


def _editable_version(job: Job) -> JobVersion:
    version = job.current_version
    if version is None or not version.is_editable:
        raise ConflictError(
            "conflict.version_locked",
            "This version is locked. Create a new version to make changes.",
        )
    return version


def _validate_tz(name: str) -> str:
    try:
        zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        raise DomainError(
            "validation_error", "Unknown timezone.", details={"timezone": ["Unknown timezone."]}
        ) from exc
    return name


def _payload(job: Job) -> dict[str, Any]:
    return {
        "job_id": str(job.pk),
        "slug": job.slug,
        "status": job.status,
        "version": job.published_version.number if job.published_version else None,
    }


# --------------------------------------------------------------------------------------------
# drafting


@transaction.atomic
def create_job(org: Organisation, *, actor: Any, data: dict[str, Any]) -> Job:
    membership = _require(actor, org, "jobs.create")
    title = str(data.get("title", "")).strip()
    if not title:
        raise DomainError(
            "validation_error", "A job title is required.", details={"title": ["Required."]}
        )
    job = Job(organisation=org, title=title, created_by=actor)
    job.slug = unique_job_slug(title, org.slug)
    _apply_header(job, data, org=org)
    job.save()
    _set_relations(job, data)
    version = JobVersion.objects.create(organisation=org, job=job, number=1)
    _apply_version_content(version, data)
    version.save()
    Rubric.objects.create(
        organisation=org,
        job_version=version,
        categories=default_rubric(),
        total_weight=100,
    )
    Questionnaire.objects.create(organisation=org, job_version=version)
    job.current_version = version
    job.save(update_fields=["current_version"])
    # The creator is the first recruiter on the vacancy (FR-M04-07).
    if membership.role in {"recruiter", "hr_manager", "org_admin"}:
        JobAssignment.objects.create(
            organisation=org, job=job, membership=membership, role_on_job="recruiter"
        )
    update_search_vector(job)
    _event(job, "created", "", actor)
    return job


DEFAULT_BANDS = [
    {"score": 0, "descriptor": "No evidence"},
    {"score": 25, "descriptor": "Limited evidence"},
    {"score": 50, "descriptor": "Partly meets the requirement"},
    {"score": 75, "descriptor": "Meets the requirement"},
    {"score": 100, "descriptor": "Exceeds the requirement"},
]
DEFAULT_WEIGHTS = {
    "technical": 35,
    "experience": 25,
    "competency": 20,
    "qualification": 10,
    "answers": 10,
}


def default_rubric() -> list[dict[str, Any]]:
    """Blueprint default weights (docs/05 §6): 35/25/20/10/10 with five evidence bands."""
    labels = dict(RubricCategory.choices)
    return [
        {"key": k, "label": labels[k], "weight": w, "bands": [dict(b) for b in DEFAULT_BANDS]}
        for k, w in DEFAULT_WEIGHTS.items()
    ]


def _apply_header(job: Job, data: dict[str, Any], *, org: Organisation) -> list[str]:
    changed: list[str] = []
    for name in HEADER_FIELDS:
        if name not in data:
            continue
        value = data[name]
        if name == "title":
            value = str(value).strip()
            if not value:
                raise DomainError(
                    "validation_error", "A job title is required.", details={"title": ["Required."]}
                )
        if name == "timezone":
            value = _validate_tz(str(value))
        if name in {"salary_min", "salary_max"} and value not in (None, ""):
            try:
                value = Decimal(str(value))
            except InvalidOperation as exc:
                raise DomainError(
                    "validation_error", "Salary must be a number.", details={name: ["Invalid."]}
                ) from exc
            if value < 0:
                raise DomainError(
                    "validation_error", "Salary cannot be negative.", details={name: ["Invalid."]}
                )
        if name in {"salary_min", "salary_max"} and value == "":
            value = None
        if name == "openings" and (not isinstance(value, int) or value < 1):
            raise DomainError(
                "validation_error",
                "At least one opening is required.",
                details={"openings": ["Must be 1 or more."]},
            )
        if name == "closes_at" and value is not None and not isinstance(value, datetime):
            raise DomainError(
                "validation_error", "Invalid deadline.", details={"closes_at": ["Invalid."]}
            )
        if getattr(job, name) != value:
            setattr(job, name, value)
            changed.append(name)
    if (
        job.salary_min is not None
        and job.salary_max is not None
        and job.salary_min > job.salary_max
    ):
        raise DomainError(
            "validation_error",
            "Minimum salary cannot exceed the maximum.",
            details={"salary_min": ["Must not exceed the maximum."]},
        )
    if "department_id" in data or "location_ids" in data:
        changed.append("structure")
    return changed


def _set_relations(job: Job, data: dict[str, Any]) -> None:
    from apps.organisations.models import Department, Location

    org = job.organisation
    if "department_id" in data:
        dep_id = data["department_id"]
        if dep_id and not Department.objects.for_org(org).filter(pk=dep_id).exists():
            raise DomainError(
                "validation_error", "Unknown department.", details={"department_id": ["Invalid."]}
            )
        job.department_id = dep_id or None
        job.save(update_fields=["department"])
    if "location_ids" in data:
        ids = list(data["location_ids"] or [])
        locations = list(Location.objects.for_org(org).filter(pk__in=ids))
        if len(locations) != len(set(map(str, ids))):
            raise DomainError(
                "validation_error", "Unknown location.", details={"location_ids": ["Invalid."]}
            )
        job.locations.set(locations)


def _apply_version_content(version: JobVersion, data: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for name in VERSION_TEXT_FIELDS:
        if name in data:
            setattr(version, name, str(data[name] or "").strip())
            changed.append(name)
    for name in VERSION_HTML_FIELDS:
        if name in data:
            setattr(version, name, sanitize_html(data[name]))  # EC-JOB-12
            changed.append(name)
    if "required_documents" in data:
        docs = list(dict.fromkeys(data["required_documents"] or []))
        unknown = [d for d in docs if d not in REQUIRED_DOCUMENT_TYPES]
        if unknown:
            raise DomainError(
                "validation_error",
                "Unknown document type.",
                details={"required_documents": [f"Unknown: {', '.join(map(str, unknown))}"]},
            )
        version.required_documents = docs
        changed.append("required_documents")
    return changed


@transaction.atomic
def update_job(job: Job, *, actor: Any, data: dict[str, Any], lock_version: int | None) -> Job:
    """PATCH: header + advert content of the current (editable) version. EC-JOB-07 lock."""
    _require(actor, job.organisation, "jobs.create")
    job = _lock(job)
    _check_lock(job, lock_version)
    version = _editable_version(job)
    if job.status not in {S.DRAFT, *LIVE, S.APPROVED}:
        raise InvalidTransitionError(message="This vacancy can no longer be edited.")
    if "closes_at" in data and job.status in LIVE:
        raise ConflictError(
            "conflict.use_extend", "Use 'extend deadline' to change the deadline of a live job."
        )
    header = _apply_header(job, data, org=job.organisation)
    if "title" in header and job.published_at is None:
        job.slug = unique_job_slug(job.title, job.organisation.slug, exclude_job_id=job.pk)
        header.append("slug")  # EC-JOB-13: slugs only change before first publish
    _set_relations(job, data)
    content = _apply_version_content(version, data)
    if content:
        version.save(update_fields=[*content, "updated_at"])
    _bump(job, *[h for h in header if h != "structure"])
    update_search_vector(job)
    audit.record(actor=actor, action="job.updated", target=job, after={"fields": header + content})
    return job


@transaction.atomic
def set_criteria(
    job: Job, *, actor: Any, criteria: list[dict[str, Any]], lock_version: int | None = None
) -> list[JobCriterion]:
    _require(actor, job.organisation, "jobs.create")
    job = _lock(job)
    _check_lock(job, lock_version)
    version = _editable_version(job)
    errors = validate_criteria(criteria)
    if errors:
        raise DomainError("validation_error", "Fix the highlighted criteria.", details=errors)
    version.criteria.all().delete()
    from apps.taxonomy.models import QualificationLevel, Skill

    saved = []
    for order, c in enumerate(criteria):
        skill_id = c.get("skill_id")
        if skill_id and not (
            Skill.objects.filter(pk=skill_id, organisation__isnull=True).exists()
            or Skill.objects.filter(pk=skill_id, organisation=job.organisation).exists()
        ):
            raise DomainError(
                "validation_error",
                "Unknown skill.",
                details={str(order): {"skill_id": ["Unknown skill."]}},
            )
        level_id = c.get("qualification_level_id")
        if level_id and not QualificationLevel.objects.filter(pk=level_id).exists():
            raise DomainError(
                "validation_error",
                "Unknown qualification level.",
                details={str(order): {"qualification_level_id": ["Unknown level."]}},
            )
        saved.append(
            JobCriterion.objects.create(
                organisation=job.organisation,
                job_version=version,
                order=order,
                type=c["type"],
                importance=c["importance"],
                title=c["title"].strip(),
                description=c.get("description", ""),
                evidence_guidance=c.get("evidence_guidance", ""),
                justification=(c.get("justification") or "").strip(),
                skill_id=skill_id or None,
                qualification_level_id=level_id or None,
                min_months=c.get("min_months"),
                equivalents=list(c.get("equivalents") or []),
                rubric_category=c.get("rubric_category") or default_category(c["type"]),
                weight_within_category=Decimal(str(c.get("weight_within_category", 1))),
            )
        )
    _bump(job)
    update_search_vector(job)
    audit.record(
        actor=actor,
        action="job.criteria_updated",
        target=job,
        after={
            "count": len(saved),
            "essential": sum(1 for c in saved if c.importance == "essential"),
        },
    )
    return saved


def default_category(criterion_type: str) -> str:
    return {
        "skill": "technical",
        "experience": "experience",
        "competency": "competency",
        "qualification": "qualification",
        "certification": "qualification",
        "licence": "qualification",
        "language": "competency",
        "eligibility": "answers",
    }.get(criterion_type, "technical")


def validate_criteria(criteria: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    errors: dict[str, dict[str, list[str]]] = {}

    def err(i: int, f: str, m: str) -> None:
        errors.setdefault(str(i), {}).setdefault(f, []).append(m)

    if len(criteria) > 40:
        err(0, "non_field_errors", "At most 40 criteria are allowed.")
    for i, c in enumerate(criteria):
        if c.get("type") not in CriterionType.values:
            err(i, "type", "Unknown criterion type.")
        if c.get("importance") not in Importance.values:
            err(i, "importance", "Choose essential or preferred.")
        if not str(c.get("title", "")).strip():
            err(i, "title", "A title is required.")
        if (
            c.get("importance") == Importance.ESSENTIAL
            and not str(c.get("justification") or "").strip()
        ):
            # FR-M04-03 / EC-JOB-03: essential requirements must be justified.
            err(i, "justification", "Explain why this is essential for the role.")
        if c.get("rubric_category") and c["rubric_category"] not in RubricCategory.values:
            err(i, "rubric_category", "Unknown rubric category.")
        months = c.get("min_months")
        if months is not None and (not isinstance(months, int) or not 0 <= months <= 600):
            err(i, "min_months", "Enter months between 0 and 600.")
        try:
            w = Decimal(str(c.get("weight_within_category", 1)))
            if not Decimal("0") < w <= Decimal("10"):
                err(i, "weight_within_category", "Weight must be between 0 and 10.")
        except InvalidOperation:
            err(i, "weight_within_category", "Weight must be a number.")
        equivalents = c.get("equivalents") or []
        if not isinstance(equivalents, list) or not all(isinstance(e, str) for e in equivalents):
            err(i, "equivalents", "Equivalents must be a list of text.")
    return errors


def validate_rubric(categories: list[dict[str, Any]]) -> dict[str, Any]:
    errors: dict[str, Any] = {}
    keys = [c.get("key") for c in categories]
    if len(set(keys)) != len(keys):
        errors["categories"] = ["Each category may appear once."]
    total = 0
    for i, c in enumerate(categories):
        e: dict[str, list[str]] = {}
        if c.get("key") not in RubricCategory.values:
            e.setdefault("key", []).append("Unknown category.")
        w = c.get("weight")
        if not isinstance(w, int) or not 0 <= w <= 100:
            e.setdefault("weight", []).append("Weight must be a whole number 0-100.")
        else:
            total += w
        bands = c.get("bands") or []
        scores = [b.get("score") for b in bands]
        if len(bands) < 2 or any(not str(b.get("descriptor", "")).strip() for b in bands):
            e.setdefault("bands", []).append("Add at least two bands with descriptors.")
        elif scores != sorted(scores) or len(set(scores)) != len(scores):
            e.setdefault("bands", []).append("Band scores must increase.")
        if e:
            errors[str(i)] = e
    if total != 100:
        # EC-JOB-02
        errors["total_weight"] = [f"Weights must add up to 100 (currently {total})."]
    return errors


@transaction.atomic
def set_rubric(
    job: Job, *, actor: Any, categories: list[dict[str, Any]], lock_version: int | None = None
) -> Rubric:
    _require(actor, job.organisation, "jobs.create")
    job = _lock(job)
    _check_lock(job, lock_version)
    version = _editable_version(job)
    errors = validate_rubric(categories)
    if errors:
        raise DomainError("validation_error", "Fix the rubric.", details=errors)
    clean = [
        {
            "key": c["key"],
            "label": str(c.get("label") or dict(RubricCategory.choices)[c["key"]]),
            "weight": c["weight"],
            "bands": [
                {"score": b["score"], "descriptor": str(b["descriptor"]).strip()}
                for b in c["bands"]
            ],
        }
        for c in categories
    ]
    rubric, _ = Rubric.objects.update_or_create(
        job_version=version,
        defaults={"organisation": job.organisation, "categories": clean, "total_weight": 100},
    )
    _bump(job)
    audit.record(
        actor=actor,
        action="job.rubric_updated",
        target=job,
        after={"weights": {c["key"]: c["weight"] for c in clean}},
    )
    return rubric


@transaction.atomic
def set_questionnaire(
    job: Job, *, actor: Any, questions: list[dict[str, Any]], lock_version: int | None = None
) -> Questionnaire:
    _require(actor, job.organisation, "jobs.create")
    job = _lock(job)
    _check_lock(job, lock_version)
    version = _editable_version(job)
    criterion_ids = {str(pk) for pk in version.criteria.values_list("pk", flat=True)}
    for i, q in enumerate(questions):
        if q.get("criterion_id") and str(q["criterion_id"]) not in criterion_ids:
            raise DomainError(
                "validation_error",
                "Linked criterion not found on this version.",
                details={str(i): {"criterion_id": ["Unknown criterion."]}},
            )
    questionnaire, _ = Questionnaire.objects.get_or_create(
        job_version=version, defaults={"organisation": job.organisation}
    )
    replace_questions(questionnaire, questions, actor=actor)
    _bump(job)
    return questionnaire


# --------------------------------------------------------------------------------------------
# readiness


@dataclass
class Check:
    id: str
    ok: bool
    message: str
    blocking: bool = True
    details: dict[str, Any] = field(default_factory=dict)


def readiness(job: Job, *, stage: str = "publish") -> dict[str, Any]:
    """Publish-readiness checklist (SRS §3.2, EC-JOB-01). ``stage`` = ``submit`` | ``publish``.

    Returns ``{"ready": bool, "checks": [...], "warnings": [...]}``; warnings never block.
    """
    version = job.current_version if stage == "submit" else _version_to_publish(job)
    checks: list[Check] = []
    org = job.organisation
    current = now()

    checks.append(Check("title", bool(job.title.strip()), "The vacancy has a title."))
    has_body = bool(version and (version.summary.strip() or version.responsibilities_html.strip()))
    checks.append(Check("description", has_body, "A summary or responsibilities are written."))
    has_location = job.workplace_type == WorkplaceType.REMOTE or job.locations.exists()
    checks.append(Check("location", has_location, "A location is set (or the job is remote)."))
    checks.append(
        Check(
            "required_documents",
            bool(version and "cv" in (version.required_documents or [])),
            "A CV is requested.",
        )
    )
    criteria = list(version.criteria.all()) if version else []
    essential = [c for c in criteria if c.importance == Importance.ESSENTIAL]
    checks.append(
        Check("essential_criterion", bool(essential), "At least one essential criterion.")
    )
    unjustified = [c.title for c in essential if not c.justification.strip()]
    checks.append(
        Check(
            "essential_justified",
            not unjustified,
            "Every essential criterion is justified.",
            details={"criteria": unjustified},
        )
    )
    rubric = getattr(version, "rubric", None) if version else None
    rubric_errors = validate_rubric(rubric.categories) if rubric else {"rubric": ["Missing."]}
    checks.append(
        Check(
            "rubric",
            not rubric_errors,
            "The rubric weights add up to 100 and every category has bands.",
            details=rubric_errors,
        )
    )
    questionnaire = getattr(version, "questionnaire", None) if version else None
    q_ok = questionnaire is not None
    q_details: dict[str, Any] = {}
    if questionnaire is not None:
        defs = [_question_dict(q) for q in questionnaire.questions.prefetch_related("options")]
        q_errors = validate_questions(defs)
        flagged = [q.key for q in blocking_questions(questionnaire)]
        q_ok = not q_errors and not flagged
        q_details = {"errors": q_errors, "protected_topics_unresolved": flagged}
    checks.append(
        Check(
            "questionnaire",
            q_ok,
            "Screening questions are valid and protected-topic questions are justified.",
            details=q_details,
        )
    )
    deadline_ok = job.closes_at is not None and job.closes_at > current
    checks.append(Check("deadline", deadline_ok, "The closing date is in the future."))
    recruiters = JobAssignment.objects.for_org(org).filter(
        job=job, role_on_job="recruiter", membership__status=Membership.Status.ACTIVE
    )
    checks.append(Check("recruiter_assigned", recruiters.exists(), "A recruiter is assigned."))
    policy = OrganisationPolicy.objects.filter(organisation=org).first()
    checks.append(
        Check(
            "privacy_notice",
            bool(policy and policy.privacy_notice.strip()),
            "The organisation has a candidate privacy notice.",
        )
    )
    if stage == "publish":
        verified = (
            org.status == Organisation.Status.ACTIVE
            and org.verified_at is not None
            and not org.is_read_only
        )
        checks.append(Check("org_verified", verified, "The organisation is verified."))
        approved = version is not None and version.status == VersionStatus.APPROVED
        checks.append(Check("approved", approved, "An HR manager approved this version."))

    warnings: list[dict[str, Any]] = []
    if criteria and len(essential) == len(criteria):
        warnings.append(
            {
                "id": "all_essential",
                "message": "Every criterion is essential, which narrows the candidate pool.",
            }
        )
    if deadline_ok and job.closes_at is not None and job.closes_at - current < SHORT_DEADLINE:
        warnings.append({"id": "short_deadline", "message": "The vacancy closes within 24 hours."})
    if questionnaire is not None:
        for q in questionnaire.questions.all():
            for w in q.protected_topic_flag:
                warnings.append(
                    {
                        "id": "protected_topic",
                        "question": q.key,
                        "justified": bool(q.protected_exception_reason.strip()),
                        **w,
                    }
                )
    return {
        "ready": all(c.ok for c in checks if c.blocking),
        "stage": stage,
        "checks": [asdict(c) for c in checks],
        "warnings": warnings,
    }


def _question_dict(q: Any) -> dict[str, Any]:
    return {
        "key": q.key,
        "type": q.type,
        "prompt": q.prompt,
        "help_text": q.help_text,
        "required": q.required,
        "config": q.config,
        "branching": q.branching,
        "scoring": q.scoring,
        "is_knockout": q.is_knockout,
        "knockout_expected": (q.config or {}).get("knockout_expected"),
        "options": [
            {"label": o.label, "value": o.value, "points": o.points} for o in q.options.all()
        ],
    }


def _version_to_publish(job: Job) -> JobVersion | None:
    return job.current_version


def _assert_ready(job: Job, stage: str) -> None:
    result = readiness(job, stage=stage)
    if not result["ready"]:
        failing = [c for c in result["checks"] if c["blocking"] and not c["ok"]]
        raise DomainError(
            "job_not_ready",
            "This vacancy is not ready yet. Resolve the items in the checklist.",
            status_code=422,
            details={"checks": failing},
        )


# --------------------------------------------------------------------------------------------
# approval


@transaction.atomic
def submit_for_approval(job: Job, *, actor: Any, note: str = "") -> Job:
    _require(actor, job.organisation, "jobs.create")
    job = _lock(job)
    version = _editable_version(job)
    _assert_ready(job, "submit")
    previous = job.status
    if job.status == S.DRAFT:
        _transition(job, {S.DRAFT}, S.IN_REVIEW, "submitted")
    elif job.status not in LIVE | {S.APPROVED}:
        raise InvalidTransitionError(message="This vacancy cannot be submitted for approval.")
    version.status = VersionStatus.IN_REVIEW
    version.submitted_by = actor
    version.submitted_at = now()
    version.change_note = note.strip()[:500] or version.change_note
    version.save(
        update_fields=["status", "submitted_by", "submitted_at", "change_note", "updated_at"]
    )
    _bump(job, "status")
    _event(job, "submitted", previous, actor, note.strip())
    return job


def _dual_control(org: Organisation) -> bool:
    policy = OrganisationPolicy.objects.filter(organisation=org).first()
    return bool(policy and policy.rubric_dual_control)


@transaction.atomic
def approve(job: Job, *, actor: Any, comment: str = "") -> Job:
    """HR manager approval freezes the version (criteria, rubric, questionnaire, snapshot)."""
    _require(actor, job.organisation, "jobs.approve")
    job = _lock(job)
    version = job.current_version
    if version is None or version.status != VersionStatus.IN_REVIEW:
        raise InvalidTransitionError(message="There is no version awaiting approval.")
    if _dual_control(job.organisation) and version.submitted_by_id == actor.pk:
        raise PermissionDeniedError(
            "dual_control", "Dual control is on: another HR manager must approve this vacancy."
        )
    _assert_ready(job, "submit")
    stamp = now()
    version.status = VersionStatus.APPROVED
    version.approved_by = actor
    version.approved_at = stamp
    version.snapshot = snapshot(job, version)
    version.save(update_fields=["status", "approved_by", "approved_at", "snapshot", "updated_at"])
    Rubric.objects.for_org(job.organisation_id).filter(job_version=version).update(
        status=RubricStatus.APPROVED, approved_by=actor, approved_at=stamp, updated_at=stamp
    )
    Questionnaire.objects.for_org(job.organisation_id).filter(job_version=version).update(
        status=Questionnaire.Status.APPROVED, updated_at=stamp
    )
    JobApproval.objects.create(
        organisation=job.organisation,
        job_version=version,
        approver=actor,
        decision=JobApproval.Decision.APPROVED,
        comment=comment.strip(),
        decided_at=stamp,
    )
    previous = job.status
    if job.status == S.IN_REVIEW:
        job.status = S.APPROVED
        _bump(job, "status")
        _event(job, "approved", previous, actor, comment.strip())
    else:
        # A new version of a live vacancy: it replaces the advert immediately (EC-JOB-06).
        old = job.published_version
        if old is not None and old.pk != version.pk:
            old.status = VersionStatus.SUPERSEDED
            old.save(update_fields=["status", "updated_at"])
        if job.status in {S.PUBLISHED, S.PAUSED}:
            job.published_version = version
        _bump(job, "published_version")
        update_search_vector(job)
        _event(job, "version_published", previous, actor, comment.strip())
        if job.status in {S.PUBLISHED, S.PAUSED}:
            outbox.emit(
                "job.version_published",
                job,
                {**_payload(job), "previous_version": old.number if old else None},
                dedupe_key=f"job.version_published:{job.pk}:{version.number}",
            )
    return job


@transaction.atomic
def reject(job: Job, *, actor: Any, reason: str) -> Job:
    _require(actor, job.organisation, "jobs.approve")
    text = _reason(reason)
    job = _lock(job)
    version = job.current_version
    if version is None or version.status != VersionStatus.IN_REVIEW:
        raise InvalidTransitionError(message="There is no version awaiting approval.")
    version.status = VersionStatus.DRAFT
    version.save(update_fields=["status", "updated_at"])
    JobApproval.objects.create(
        organisation=job.organisation,
        job_version=version,
        approver=actor,
        decision=JobApproval.Decision.CHANGES_REQUESTED,
        comment=text,
        decided_at=now(),
    )
    previous = job.status
    if job.status == S.IN_REVIEW:
        job.status = S.DRAFT
    _bump(job, "status")
    _event(job, "changes_requested", previous, actor, text)
    return job


def snapshot(job: Job, version: JobVersion) -> dict[str, Any]:
    """Frozen advert + scoring definition at approval time (principle 5)."""
    rubric = getattr(version, "rubric", None)
    questionnaire = getattr(version, "questionnaire", None)
    return {
        "title": job.title,
        "employment_type": job.employment_type,
        "workplace_type": job.workplace_type,
        "seniority": job.seniority,
        "openings": job.openings,
        "salary": {
            "min": str(job.salary_min) if job.salary_min is not None else None,
            "max": str(job.salary_max) if job.salary_max is not None else None,
            "currency": job.salary_currency,
            "period": job.salary_period,
            "disclosed": job.salary_disclosed,
        },
        "locations": sorted(str(pk) for pk in job.locations.values_list("pk", flat=True)),
        "summary": version.summary,
        "responsibilities_html": version.responsibilities_html,
        "requirements_html": version.requirements_html,
        "benefits_html": version.benefits_html,
        "required_documents": version.required_documents,
        "criteria": [
            {
                "id": str(c.pk),
                "type": c.type,
                "importance": c.importance,
                "title": c.title,
                "justification": c.justification,
                "skill_id": str(c.skill_id) if c.skill_id else None,
                "min_months": c.min_months,
                "equivalents": c.equivalents,
                "rubric_category": c.rubric_category,
                "weight_within_category": str(c.weight_within_category),
            }
            for c in version.criteria.all()
        ],
        "rubric": rubric.categories if rubric else [],
        "questions": [
            {
                **_question_dict(q),
                "options": [
                    {
                        "label": o.label,
                        "value": o.value,
                        "points": str(o.points) if o.points is not None else None,
                    }
                    for o in q.options.all()
                ],
            }
            for q in (questionnaire.questions.prefetch_related("options") if questionnaire else [])
        ],
    }


# --------------------------------------------------------------------------------------------
# publishing lifecycle


def _publish_now(job: Job, actor: Any, from_status: str, *, reason: str = "") -> None:
    stamp = now()
    job.status = S.PUBLISHED
    job.published_version = job.current_version
    job.published_at = job.published_at or stamp
    job.publish_at = None
    _bump(job, "status", "published_version", "published_at", "publish_at")
    update_search_vector(job)
    _event(job, "published", from_status, actor, reason)
    outbox.emit(
        "job.published",
        job,
        _payload(job),
        dedupe_key=f"job.published:{job.pk}:{_payload(job)['version'] or 0}",
    )


@transaction.atomic
def publish(job: Job, *, actor: Any) -> Job:
    _require(actor, job.organisation, "jobs.publish")
    job = _lock(job)
    if job.status not in {S.APPROVED, S.SCHEDULED}:
        raise InvalidTransitionError(message="Only an approved vacancy can be published.")
    assert_can_publish(job.organisation)
    _assert_ready(job, "publish")
    _publish_now(job, actor, job.status)
    return job


@transaction.atomic
def schedule(job: Job, *, actor: Any, publish_at: datetime) -> Job:
    _require(actor, job.organisation, "jobs.publish")
    job = _lock(job)
    if job.status not in {S.APPROVED, S.SCHEDULED}:
        raise InvalidTransitionError(message="Only an approved vacancy can be scheduled.")
    if publish_at <= now():
        raise DomainError(
            "validation_error",
            "The publish time must be in the future.",
            details={"publish_at": ["Must be in the future."]},
        )
    if job.closes_at is not None and publish_at >= job.closes_at:
        raise DomainError(
            "validation_error",
            "The vacancy must be published before it closes.",
            details={"publish_at": ["Must be before the closing date."]},
        )
    assert_can_publish(job.organisation)
    _assert_ready(job, "publish")
    previous = job.status
    job.status = S.SCHEDULED
    job.publish_at = publish_at
    _bump(job, "status", "publish_at")
    _event(job, "scheduled", previous, actor, audit_after={"publish_at": publish_at.isoformat()})
    return job


def publish_scheduled(job: Job) -> bool:
    """Beat-driven publish (P03-T06). Idempotent: returns False when nothing to do."""
    with transaction.atomic():
        job = _lock(job)
        if job.status != S.SCHEDULED or job.publish_at is None or job.publish_at > now():
            return False
        try:
            assert_can_publish(job.organisation)
        except (OrgUnverifiedError, DomainError) as exc:
            previous = job.status
            job.status = S.APPROVED
            job.publish_at = None
            _bump(job, "status", "publish_at")
            _event(job, "schedule_cancelled", previous, None, exc.message)
            return False
        if job.closes_at is not None and job.closes_at <= now():
            previous = job.status
            job.status = S.APPROVED
            job.publish_at = None
            _bump(job, "status", "publish_at")
            _event(job, "schedule_cancelled", previous, None, "Closing date already passed.")
            return False
        _publish_now(job, None, S.SCHEDULED, reason="Scheduled publish")
        return True


@transaction.atomic
def pause(job: Job, *, actor: Any, reason: str = "") -> Job:
    _require(actor, job.organisation, "jobs.publish")
    job = _lock(job)
    previous = _transition(job, {S.PUBLISHED}, S.PAUSED, "paused")
    _bump(job, "status")
    _event(job, "paused", previous, actor, (reason or "").strip())
    outbox.emit(
        "job.paused", job, _payload(job), dedupe_key=f"job.paused:{job.pk}:{job.lock_version}"
    )
    return job


@transaction.atomic
def resume(job: Job, *, actor: Any) -> Job:
    _require(actor, job.organisation, "jobs.publish")
    job = _lock(job)
    if job.closes_at is not None and job.closes_at <= now():
        raise DomainError(
            "deadline_passed",
            "The closing date has passed. Extend the deadline to reopen this vacancy.",
            status_code=422,
        )
    assert_can_publish(job.organisation)
    previous = _transition(job, {S.PAUSED}, S.PUBLISHED, "resumed")
    _bump(job, "status")
    _event(job, "resumed", previous, actor)
    outbox.emit(
        "job.resumed", job, _payload(job), dedupe_key=f"job.resumed:{job.pk}:{job.lock_version}"
    )
    return job


def _close(job: Job, actor: Any, reason: str, *, automatic: bool) -> None:
    previous = _transition(job, {S.PUBLISHED, S.PAUSED, S.SCHEDULED}, S.CLOSED, "closed")
    job.closed_at = now()
    job.close_reason = reason[:255]
    job.publish_at = None
    _bump(job, "status", "closed_at", "close_reason", "publish_at")
    _event(job, "auto_closed" if automatic else "closed", previous, actor, reason)
    outbox.emit(
        "job.closed",
        job,
        {**_payload(job), "automatic": automatic, "early": not automatic},
        dedupe_key=f"job.closed:{job.pk}:{job.lock_version}",
    )


@transaction.atomic
def close(job: Job, *, actor: Any, reason: str) -> Job:
    """Close early (EC-JOB-10): drafts are abandoned downstream via ``job.closed``."""
    _require(actor, job.organisation, "jobs.publish")
    text = _reason(reason)
    job = _lock(job)
    _close(job, actor, text, automatic=False)
    return job


def auto_close(job: Job) -> bool:
    """Beat-driven close at the deadline (P03-T06). Idempotent."""
    with transaction.atomic():
        job = _lock(job)
        if job.status not in {S.PUBLISHED, S.PAUSED} or job.closes_at is None:
            return False
        if job.closes_at > now():
            return False
        _close(job, None, "Closing date reached", automatic=True)
        return True


@transaction.atomic
def archive(job: Job, *, actor: Any, reason: str = "") -> Job:
    """EC-JOB-11: vacancies are never hard-deleted once used; archive instead."""
    _require(actor, job.organisation, "jobs.publish")
    job = _lock(job)
    previous = _transition(job, {S.DRAFT, S.CLOSED, S.APPROVED}, S.ARCHIVED, "archived")
    _bump(job, "status")
    _event(job, "archived", previous, actor, (reason or "").strip())
    return job


@transaction.atomic
def extend_deadline(job: Job, *, actor: Any, closes_at: datetime, reason: str) -> Job:
    """EC-JOB-09/16: extend a live or closed vacancy. A closed vacancy reopens."""
    _require(actor, job.organisation, "jobs.publish")
    text = _reason(reason)
    job = _lock(job)
    if job.status not in {S.APPROVED, S.SCHEDULED, S.PUBLISHED, S.PAUSED, S.CLOSED}:
        raise InvalidTransitionError(message="This vacancy's deadline cannot be extended.")
    if closes_at <= now():
        raise DomainError(
            "validation_error",
            "The new closing date must be in the future.",
            details={"closes_at": ["Must be in the future."]},
        )
    if job.closes_at is not None and closes_at <= job.closes_at:
        raise DomainError(
            "validation_error",
            "The new closing date must be later than the current one.",
            details={"closes_at": ["Must be later than the current deadline."]},
        )
    old = job.closes_at
    previous = job.status
    if job.status == S.CLOSED:
        assert_can_publish(job.organisation)
        job.status = S.PUBLISHED
        job.closed_at = None
        job.close_reason = ""
    job.closes_at = closes_at
    _bump(job, "status", "closes_at", "closed_at", "close_reason")
    _event(
        job,
        "deadline_extended",
        previous,
        actor,
        text,
        audit_after={
            "closes_at": closes_at.isoformat(),
            "previous": old.isoformat() if old else None,
        },
    )
    outbox.emit(
        "job.deadline_extended",
        job,
        {**_payload(job), "closes_at": closes_at.isoformat(), "reopened": previous == S.CLOSED},
        dedupe_key=f"job.deadline_extended:{job.pk}:{job.lock_version}",
    )
    return job


def _copy_version(source: JobVersion, target: JobVersion) -> None:
    org = target.organisation
    for name in (*VERSION_TEXT_FIELDS, *VERSION_HTML_FIELDS, "required_documents"):
        setattr(target, name, getattr(source, name))
    target.change_note = ""
    target.save()
    mapping: dict[Any, JobCriterion] = {}
    for c in source.criteria.all():
        old_pk = c.pk
        c.pk = None
        c.id = None
        c._state.adding = True
        c.job_version = target
        c.organisation = org
        c.save()
        mapping[old_pk] = c
    rubric = getattr(source, "rubric", None)
    Rubric.objects.create(
        organisation=org,
        job_version=target,
        categories=rubric.categories if rubric else default_rubric(),
        total_weight=100,
        version=(rubric.version + 1) if rubric else 1,
    )
    questionnaire = Questionnaire.objects.create(organisation=org, job_version=target)
    src_q = getattr(source, "questionnaire", None)
    if src_q is not None:
        from apps.questionnaires.models import Question, QuestionOption

        questionnaire.version = src_q.version + 1
        questionnaire.save(update_fields=["version"])
        for q in src_q.questions.prefetch_related("options"):
            options = list(q.options.all())
            criterion = mapping.get(q.criterion_id) if q.criterion_id else None
            new_q = Question.objects.create(
                organisation=org,
                questionnaire=questionnaire,
                key=q.key,
                section=q.section,
                order=q.order,
                type=q.type,
                prompt=q.prompt,
                help_text=q.help_text,
                required=q.required,
                config=q.config,
                branching=q.branching,
                scoring=q.scoring,
                is_knockout=q.is_knockout,
                criterion=criterion,
                protected_topic_flag=flags_for(_question_dict(q)),
                protected_exception_reason=q.protected_exception_reason,
            )
            for o in options:
                QuestionOption.objects.create(
                    organisation=org,
                    question=new_q,
                    order=o.order,
                    label=o.label,
                    value=o.value,
                    points=o.points,
                )


@transaction.atomic
def new_version(job: Job, *, actor: Any, reason: str) -> JobVersion:
    """EC-JOB-06: draft version N+1 from the live/approved one. Applications keep their version."""
    _require(actor, job.organisation, "jobs.approve")
    text = _reason(reason)
    job = _lock(job)
    if job.status not in {S.APPROVED, *LIVE}:
        raise InvalidTransitionError(message="Only approved or live vacancies get new versions.")
    source = job.current_version
    if source is None or source.is_editable or source.status == VersionStatus.IN_REVIEW:
        raise ConflictError(
            "conflict.draft_exists", "A draft version already exists for this vacancy."
        )
    number = (job.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    version = JobVersion(organisation=job.organisation, job=job, number=number)
    _copy_version(source, version)
    version.change_note = text[:500]
    version.save(update_fields=["change_note"])
    if job.status in {S.APPROVED, S.SCHEDULED}:
        # Not yet public: the previous approval is superseded and the job returns to draft.
        source.status = VersionStatus.SUPERSEDED
        source.save(update_fields=["status", "updated_at"])
        previous = job.status
        job.status = S.DRAFT
        job.publish_at = None
    else:
        previous = job.status
    job.current_version = version
    _bump(job, "current_version", "status", "publish_at")
    _event(job, "version_created", previous, actor, text, audit_after={"version": number})
    return version


@transaction.atomic
def duplicate(job: Job, *, actor: Any, title: str | None = None) -> Job:
    """EC-JOB-14: repost as a new draft vacancy. Previous applicants are not moved."""
    _require(actor, job.organisation, "jobs.create")
    source = job.published_version or job.current_version
    new_title = (title or job.title).strip()
    data = {name: getattr(job, name) for name in HEADER_FIELDS if name != "closes_at"}
    data["title"] = new_title
    copy = create_job(job.organisation, actor=actor, data=data)
    copy.department_id = job.department_id
    copy.save(update_fields=["department"])
    copy.locations.set(job.locations.all())
    draft = copy.current_version
    assert draft is not None
    # Replace the default rubric/questionnaire with copies of the source version.
    Rubric.objects.for_org(job.organisation_id).filter(job_version=draft).delete()
    Questionnaire.objects.for_org(job.organisation_id).filter(job_version=draft).delete()
    if source is not None:
        _copy_version(source, draft)
    update_search_vector(copy)
    _event(copy, "duplicated", "", actor, audit_after={"source_job": str(job.pk)})
    return copy

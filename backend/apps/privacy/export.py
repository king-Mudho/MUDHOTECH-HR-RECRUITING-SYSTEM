"""Personal data export bundle (P09-T03, EC-PRV-03; CDPA right of access).

For a confirmed access/export request the ``reports`` worker builds one ZIP in the private
``exports`` bucket:

* ``data.json`` - profile, applications (answers, extracted CV facts, AI-assisted evaluation
  summaries, status history with reasons, shortlist decisions), messages, consents, requests;
* ``summary.pdf`` - the same, readable;
* ``documents/`` - the person's own original files.

Scope: the requesting organisation's records (or everything for an account-level request). Staff
identities are not included (only roles), nor other candidates' data. The download link is valid for
24 hours; downloading is audited and access-logged.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import timedelta
from html import escape
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core import storage
from apps.core.time import now

from .models import ConsentRecord, RightsRequest

EXPORT_TTL = timedelta(hours=24)
EXPORT_TYPES = (RightsRequest.Type.ACCESS, RightsRequest.Type.EXPORT)


def export_key(request: RightsRequest) -> str:
    return f"privacy/{request.export_document_id}.zip"


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def collect(request: RightsRequest) -> dict[str, Any]:
    from apps.applications.models import Application, ApplicationStatusEvent
    from apps.candidates.models import CandidateProfile
    from apps.messaging.models import Message
    from apps.questionnaires.models import QuestionResponse
    from apps.screening.models import CriterionResult, Evaluation
    from apps.shortlisting.models import ShortlistEntry

    user = request.user
    if user is None:  # the account was deleted
        raise ValueError("export needs the requester's account")
    apps = Application.objects.unscoped().filter(candidate_user=user).exclude(status="draft")
    if request.organisation_id is not None:
        apps = apps.filter(organisation_id=request.organisation_id)
    profile = CandidateProfile.objects.filter(user=user).first()
    out: dict[str, Any] = {
        "generated_at": now().isoformat(),
        "request_reference": request.reference,
        "account": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        "profile": None,
        "applications": [],
        "consents": [],
    }
    if profile is not None:
        out["profile"] = {
            "headline": profile.headline,
            "summary": profile.summary,
            "city": profile.city,
            "country": profile.country,
            "phone": profile.phone_e164,
            "experience": [
                {
                    "title": e.title,
                    "employer": e.employer,
                    "start": _iso(e.start_date),
                    "end": _iso(e.end_date),
                }
                for e in profile.experiences.all()
            ],
            "education": [
                {"qualification": e.qualification_text, "institution": e.institution}
                for e in profile.educations.all()
            ],
            "skills": [s.raw_name for s in profile.skills.all()],
        }
    for app in apps.select_related("job", "organisation"):
        org = app.organisation_id
        answers = [
            {"question": r.question.prompt, "answer": r.value}
            for r in QuestionResponse.objects.unscoped()
            .filter(application=app)
            .select_related("question")
        ]
        evaluations = []
        if not app.objects_to_automated_processing:
            for ev in Evaluation.objects.unscoped().filter(application=app).order_by("version"):
                evaluations.append(
                    {
                        "version": ev.version,
                        "created_at": _iso(ev.created_at),
                        "note": "AI-assisted suggestion reviewed by people; not a decision.",
                        "band": ev.band,
                        "score": float(ev.total_score) if ev.total_score is not None else None,
                        "criteria": [
                            {
                                "criterion": r.criterion.title,
                                "evidence": r.evidence_status,
                                "score": float(r.score) if r.score is not None else None,
                            }
                            for r in CriterionResult.objects.unscoped()
                            .filter(evaluation=ev)
                            .select_related("criterion")
                        ],
                    }
                )
        history = [
            {
                "from": e.from_status,
                "to": e.to_status,
                "by": "you" if e.actor_id == user.pk else e.actor_type,
                "reason": e.reason_text,
                "at": _iso(e.at),
            }
            for e in ApplicationStatusEvent.objects.unscoped()
            .filter(application=app)
            .order_by("at")
        ]
        decisions = [
            {
                "decision": d.decision,
                "reason": d.reason_text or d.reason_code,
                "at": _iso(d.decided_at),
            }
            for d in ShortlistEntry.objects.unscoped().filter(
                application=app, shortlist__status="approved"
            )
        ]
        messages = [
            {"from": m.sender_role, "body": m.body, "at": _iso(m.created_at)}
            for m in Message.objects.unscoped()
            .filter(thread__application=app)
            .order_by("created_at")
        ]
        out["applications"].append(
            {
                "reference": app.reference,
                "organisation": app.organisation.name,
                "job_title": app.job.title,
                "status": app.status,
                "submitted_at": _iso(app.submitted_at),
                "objected_to_automated_processing": app.objects_to_automated_processing,
                "answers": answers,
                "evaluations": evaluations,
                "status_history": history,
                "decisions": decisions,
                "messages": messages,
                "_organisation_id": str(org),
                "_id": str(app.pk),
            }
        )
    consents = ConsentRecord.objects.filter(user=user)
    if request.organisation_id is not None:
        consents = consents.filter(organisation_id=request.organisation_id)
    out["consents"] = [
        {
            "purpose": c.purpose,
            "granted": c.granted,
            "notice_version": c.notice_version,
            "at": _iso(c.granted_at),
            "withdrawn_at": _iso(c.withdrawn_at),
        }
        for c in consents
    ]
    return out


def _documents(request: RightsRequest, app_ids: list[str]) -> list[tuple[str, bytes]]:
    from apps.applications.models import ApplicationDocument

    files = []
    links = (
        ApplicationDocument.objects.unscoped()
        .filter(application_id__in=app_ids)
        .select_related("document")
    )
    seen = set()
    for link in links:
        doc = link.document
        if doc.pk in seen or doc.owner_user_id != request.user_id:
            continue
        seen.add(doc.pk)
        try:
            data = storage.get_bytes(doc.bucket or "documents", doc.storage_key)
        except Exception:  # a missing file never blocks the export; it is logged
            import logging

            logging.getLogger("mhrs.privacy").warning(
                "export: document unavailable", extra={"document_id": str(doc.pk)}
            )
            continue
        safe = doc.original_filename.replace("/", "_").replace("\\", "_")[:120]
        files.append((f"documents/{str(doc.pk)[:8]}-{safe}", data))
    return files


def _pdf(data: dict[str, Any]) -> bytes:
    import pymupdf

    parts = [
        "<h1>Your personal data</h1>",
        f"<p>Request {escape(data['request_reference'])}, "
        f"generated {escape(data['generated_at'])}.</p>",
        f"<p>Account: {escape(data['account']['email'])}</p>",
    ]
    for app in data["applications"]:
        parts.append(
            f"<h2>{escape(app['job_title'])} at {escape(app['organisation'])}</h2>"
            f"<p>Reference {escape(str(app['reference']))}; status {escape(app['status'])}.</p>"
        )
        for h in app["status_history"]:
            parts.append(
                f"<p>{escape(str(h['at']))}: {escape(h['from'])} → {escape(h['to'])}"
                f"{' — ' + escape(h['reason']) if h['reason'] else ''}</p>"
            )
        for ev in app["evaluations"]:
            parts.append(
                f"<p>AI-assisted evaluation v{ev['version']} (reviewed by people): band "
                f"{escape(str(ev['band']))}.</p>"
            )
    parts.append("<h2>Consents</h2>")
    for c in data["consents"]:
        parts.append(
            f"<p>{escape(c['purpose'])}: {'given' if c['granted'] else 'not given'}"
            f"{' (withdrawn)' if c['withdrawn_at'] else ''}</p>"
        )
    story = pymupdf.Story(
        html="<body>" + "".join(parts) + "</body>", user_css="body{font-size:9pt}"
    )
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    page = pymupdf.paper_rect("a4")
    area = pymupdf.Rect(page.x0 + 36, page.y0 + 36, page.x1 - 36, page.y1 - 36)
    more = True
    while more:
        device = writer.begin_page(page)
        more, _ = story.place(area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()


def build(request_id: Any) -> RightsRequest | None:
    """Idempotent: an existing unexpired export is kept."""
    request = RightsRequest.objects.filter(pk=request_id).select_related("user").first()
    if request is None or request.user is None or request.type not in EXPORT_TYPES:
        return None
    if (
        request.export_document_id
        and request.export_expires_at
        and request.export_expires_at > now()
    ):
        return request
    data = collect(request)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        clean = json.loads(json.dumps(data, default=str))
        for app in clean["applications"]:
            app.pop("_organisation_id", None)
        archive.writestr("data.json", json.dumps(clean, indent=2, ensure_ascii=False))
        archive.writestr("summary.pdf", _pdf(clean))
        for name, content in _documents(request, [a["_id"] for a in data["applications"]]):
            archive.writestr(name, content)
    with transaction.atomic():
        request.export_document_id = uuid.uuid4()
        request.export_expires_at = now() + EXPORT_TTL
        storage.put_bytes("exports", export_key(request), buffer.getvalue(), "application/zip")
        request.save(update_fields=["export_document_id", "export_expires_at", "updated_at"])
        audit.record(
            action="privacy.export_built",
            actor_type="system",
            target=("rights_request", str(request.pk)),
            organisation=request.organisation_id,
            after={"applications": len(data["applications"]), "bytes": len(buffer.getvalue())},
        )
    return request


def download_url(user: Any, request_id: Any) -> str:
    from apps.core.exceptions import ConflictError, NotFoundError

    request = RightsRequest.objects.filter(pk=request_id, user=user).first()
    if request is None or not request.export_document_id:
        raise NotFoundError()
    if not request.export_expires_at or request.export_expires_at <= now():
        raise ConflictError(code="conflict.export_expired", message="This download has expired.")
    audit.record(
        actor=user,
        action="privacy.export_downloaded",
        target=("rights_request", str(request.pk)),
        organisation=request.organisation_id,
    )
    audit.log_access(user=user, target=("rights_request", request.pk), action="export_download")
    return storage.presign_get(
        "exports", export_key(request), filename=f"my-data-{request.reference}.zip"
    )

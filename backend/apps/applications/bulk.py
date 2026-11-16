"""Bulk actions on a vacancy's applicants (P08-T05, docs/08 §3.2).

Each action runs per application through the same service a single action uses (permissions,
audit, notifications), so a bulk action can never do more than the person could do one by one.
Applications the person cannot see or act on are reported as skipped with a reason; nothing
consequential happens in bulk here - "propose shortlist" only creates a draft for approval.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction

from apps.core.exceptions import DomainError, NotFoundError, PermissionDeniedError
from apps.core.time import now
from apps.organisations import rbac

MAX_BULK = 500
ACTIONS = ("assign_me", "unassign", "tag", "untag", "clarification", "propose_shortlist")


def _skip(app_id: Any, exc: Exception) -> dict[str, str]:
    code = getattr(exc, "code", "") or type(exc).__name__
    return {"application_id": str(app_id), "reason": str(code)[:60]}


def run(
    membership: Any,
    actor: Any,
    job_id: Any,
    *,
    action: str,
    application_ids: list[Any],
    tags: list[str] | None = None,
    questions: list[dict[str, Any]] | None = None,
    message: str = "",
    due_days: int = 5,
) -> dict[str, Any]:
    from apps.jobs.assignments import jobs_visible_to

    from . import ats
    from .hr import applications_visible_to

    if action not in ACTIONS:
        raise DomainError("validation_error", "Unknown action.", details={"action": [action]})
    if not rbac.can(membership.role, "applications.transition"):
        raise PermissionDeniedError(message="You can't change these applications.")
    ids = list(dict.fromkeys(str(i) for i in application_ids))
    if not ids or len(ids) > MAX_BULK:
        raise DomainError(
            "validation_error",
            f"Choose between 1 and {MAX_BULK} applications.",
            details={"application_ids": [f"Between 1 and {MAX_BULK}."]},
        )
    job = jobs_visible_to(membership).filter(pk=job_id).first()
    if job is None:
        raise NotFoundError()
    visible = {
        str(pk)
        for pk in applications_visible_to(membership)
        .filter(job=job, pk__in=ids)
        .values_list("pk", flat=True)
    }
    skipped = [{"application_id": i, "reason": "not_found"} for i in ids if i not in visible]
    targets = [i for i in ids if i in visible]
    done = 0
    result: dict[str, Any] = {"action": action, "shortlist_id": None}

    if action == "propose_shortlist":
        from apps.shortlisting import services as shortlists

        shortlist = shortlists.create_proposal(membership, actor, job.pk)
        in_list = {
            str(a)
            for a in shortlists.entries_of(shortlist).values_list("application_id", flat=True)
        }
        chosen = [i for i in targets if i in in_list]
        skipped += [
            {"application_id": i, "reason": "not_reviewable"} for i in targets if i not in in_list
        ]
        if chosen:
            # the person picked these: record them as their shortlist decisions (draft only)
            shortlists.set_decisions(
                membership,
                actor,
                shortlist.pk,
                [{"application_id": i, "decision": "shortlist"} for i in chosen],
            )
        result |= {"shortlist_id": str(shortlist.pk), "done": len(chosen), "skipped": skipped}
        return result

    for app_id in targets:
        try:
            with transaction.atomic():
                if action == "assign_me":
                    ats.assign(membership, actor, app_id, actor.pk)
                elif action == "unassign":
                    ats.assign(membership, actor, app_id, None)
                elif action in ("tag", "untag"):
                    app = ats._visible(membership, app_id)
                    wanted = ats.normalise_tags(tags or [])
                    current = list(app.tags)
                    new = (
                        list(dict.fromkeys([*current, *wanted]))
                        if action == "tag"
                        else [t for t in current if t not in wanted]
                    )
                    ats.set_tags(membership, actor, app_id, new)
                elif action == "clarification":
                    from apps.messaging import services as messaging

                    messaging.request_clarification(
                        membership,
                        actor,
                        app_id,
                        questions=questions or [],
                        due_at=now() + timedelta(days=max(1, min(due_days, 30))),
                        message=message,
                    )
            done += 1
        except DomainError as exc:
            if action == "clarification" and exc.code == "validation_error" and not done:
                raise  # the questions themselves are invalid: tell the person once
            skipped.append(_skip(app_id, exc))
    result |= {"done": done, "skipped": skipped}
    return result

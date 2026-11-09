"""Questionnaire services: save definitions, protected-topic flags and exceptions (P03-T03/T04)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from apps.audit import services as audit
from apps.core.exceptions import ConflictError, DomainError, PermissionDeniedError
from apps.organisations import rbac
from apps.organisations.selectors import active_membership

from .linter import lint_question
from .models import Question, Questionnaire, QuestionOption
from .validation import validate_questions

MIN_EXCEPTION_REASON = 20


def flags_for(question: Question | dict[str, Any]) -> list[dict[str, str]]:
    if isinstance(question, Question):
        prompt, help_text = question.prompt, question.help_text
        labels = list(question.options.values_list("label", flat=True)) if question.pk else []
    else:
        prompt, help_text = question.get("prompt", ""), question.get("help_text", "")
        labels = [str(o.get("label", "")) for o in question.get("options") or []]
    return [w.as_dict() for w in lint_question(prompt, help_text, labels)]


def _points(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise DomainError("validation_error", "Option points must be numbers.") from exc


@transaction.atomic
def replace_questions(
    questionnaire: Questionnaire, questions: list[dict[str, Any]], *, actor: Any
) -> list[Question]:
    """Replace the whole definition (builder saves the full list). Draft questionnaires only.

    Protected-topic flags are recomputed; an existing exception reason survives only while the
    question text is unchanged (editing the wording requires a fresh justification).
    """
    if questionnaire.status != Questionnaire.Status.DRAFT:
        raise ConflictError("conflict.locked", "Approved questionnaires cannot be edited.")
    errors = validate_questions(questions)
    if errors:
        raise DomainError("validation_error", "Fix the highlighted questions.", details=errors)
    previous = {q.key: q for q in questionnaire.questions.all()}
    questionnaire.questions.all().delete()
    org = questionnaire.organisation
    saved: list[Question] = []
    for order, data in enumerate(questions):
        flags = flags_for(data)
        old = previous.get(data["key"])
        keep_reason = (
            old is not None
            and flags
            and old.prompt == data["prompt"]
            and old.help_text == data.get("help_text", "")
        )
        scoring = dict(data.get("scoring") or {"mode": "none"})
        config = dict(data.get("config") or {})
        if data.get("is_knockout"):
            config["knockout_expected"] = data.get("knockout_expected")
        question = Question.objects.create(
            organisation=org,
            questionnaire=questionnaire,
            key=data["key"],
            section=data.get("section", ""),
            order=order,
            type=data["type"],
            prompt=data["prompt"],
            help_text=data.get("help_text", ""),
            required=bool(data.get("required", True)),
            config=config,
            branching=data.get("branching") or {},
            scoring=scoring,
            is_knockout=bool(data.get("is_knockout")),
            criterion_id=data.get("criterion_id"),
            protected_topic_flag=flags,
            protected_exception_reason=old.protected_exception_reason
            if keep_reason and old
            else "",
        )
        for i, opt in enumerate(data.get("options") or []):
            QuestionOption.objects.create(
                organisation=org,
                question=question,
                order=i,
                label=opt["label"],
                value=opt["value"],
                points=_points(opt.get("points")),
            )
        saved.append(question)
    audit.record(
        actor=actor,
        action="questionnaire.updated",
        target=questionnaire,
        after={"questions": len(saved), "flagged": sum(1 for q in saved if q.blocks_publishing)},
    )
    return saved


@transaction.atomic
def record_protected_exception(question: Question, *, actor: Any, reason: str) -> Question:
    """HR manager / admin justifies a flagged question (e.g. statutory minimum age). Audited."""
    membership = active_membership(actor, question.organisation_id)
    if membership is None or not rbac.can(membership.role, "questions.protected_exception"):
        raise PermissionDeniedError(
            message="Only an HR manager or organisation admin can approve this question."
        )
    question = (
        Question.objects.for_org(question.organisation_id).select_for_update().get(pk=question.pk)
    )
    if question.questionnaire.status != Questionnaire.Status.DRAFT:
        raise ConflictError("conflict.locked", "Approved questionnaires cannot be edited.")
    if not question.protected_topic_flag:
        raise DomainError("validation_error", "This question has no protected-topic warning.")
    reason = (reason or "").strip()
    if len(reason) < MIN_EXCEPTION_REASON:
        raise DomainError(
            "validation_error",
            "Explain the lawful basis for asking this question.",
            details={"reason": [f"At least {MIN_EXCEPTION_REASON} characters."]},
        )
    before = question.protected_exception_reason
    question.protected_exception_reason = reason
    question.save(update_fields=["protected_exception_reason", "updated_at"])
    audit.record(
        actor=actor,
        action="question.protected_exception_recorded",
        target=question,
        before={"reason": before},
        after={"topics": [f["topic"] for f in question.protected_topic_flag], "reason": reason},
        reason=reason,
    )
    return question


def blocking_questions(questionnaire: Questionnaire | None) -> list[Question]:
    if questionnaire is None:
        return []
    return [q for q in questionnaire.questions.all() if q.blocks_publishing]

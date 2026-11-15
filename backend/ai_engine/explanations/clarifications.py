"""Clarification suggestions (P07-T06, docs/05 §11, EC-AI-03/04).

Suggested questions HR may send (never sent automatically): one per unknown essential, per
item that needs verification, and per CV/answer conflict. Wording is neutral and asks the
candidate to add evidence - it never implies a gap is confirmed.
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_engine.contracts import Contract, CriterionSpec, CriterionType, EvidenceStatus
from ai_engine.evaluation.engine import EvaluationResult


class Clarification(Contract):
    criterion_id: str
    reason: str  # missing_essential | needs_verification | conflict:<kind>
    question: str


ASK_MISSING = {
    CriterionType.SKILL: "Could you tell us about your experience with {title}, with an example?",
    CriterionType.EXPERIENCE: "Could you describe your experience relevant to {title}, "
    "including roles and dates?",
    CriterionType.QUALIFICATION: "Could you share details of your qualifications relevant to "
    "{title} (name, institution, year)?",
    CriterionType.CERTIFICATION: "Do you hold {title}? If so, please share the certificate "
    "and its dates.",
    CriterionType.LICENCE: "Do you hold {title}? If so, please share the licence details.",
    CriterionType.LANGUAGE: "Could you tell us about your proficiency in {title}?",
    CriterionType.COMPETENCY: "Could you give an example that shows {title}?",
    CriterionType.ELIGIBILITY: "Could you confirm: {title}?",
}
ASK_VERIFY = {
    "foreign_qualification": "Please share a copy of your {title} certificate and, if you have "
    "it, an evaluation of the qualification so we can confirm its level.",
    "expired": "Your {title} appears to have expired. Do you have a renewed certificate?",
    "roles_without_dates": "Could you add start and end dates for your roles relevant to {title}?",
    "level_unknown": "Could you tell us more about your qualification for {title} (level, "
    "institution, year)?",
}
ASK_CONFLICT = {
    "experience_years": "Your CV shows about {cv} of relevant experience and your answer says "
    "{answer}. Could you clarify, for example with roles we may have missed?",
    "skill_years": "Your CV mentions {cv} with {title} and your answer says {answer}. "
    "Could you clarify?",
    "qualification_level": "Your answer mentions a qualification ({answer}) we did not find in "
    "your CV ({cv}). Could you share details?",
}


def suggest(result: EvaluationResult, specs: Sequence[CriterionSpec]) -> list[Clarification]:
    by_id = {r.criterion_id: r for r in result.criteria}
    out: list[Clarification] = []
    for conflict in result.conflicts:
        spec = next((s for s in specs if s.id == conflict.criterion_id), None)
        template = ASK_CONFLICT.get(conflict.kind)
        if spec is None or template is None:
            continue
        out.append(
            Clarification(
                criterion_id=spec.id,
                reason=f"conflict:{conflict.kind}",
                question=template.format(
                    title=spec.title, cv=conflict.cv_value, answer=conflict.answer_value
                ),
            )
        )
    conflicted = {c.criterion_id for c in out}
    for spec in specs:
        result_ = by_id.get(spec.id)
        if result_ is None or spec.id in conflicted:
            continue
        if result_.status == EvidenceStatus.NEEDS_VERIFICATION:
            template = ASK_VERIFY.get(result_.reason)
            if template:
                out.append(
                    Clarification(
                        criterion_id=spec.id,
                        reason="needs_verification",
                        question=template.format(title=spec.title),
                    )
                )
        elif spec.essential and result_.status == EvidenceStatus.MISSING:
            out.append(
                Clarification(
                    criterion_id=spec.id,
                    reason="missing_essential",
                    question=ASK_MISSING[spec.type].format(title=spec.title),
                )
            )
    return out

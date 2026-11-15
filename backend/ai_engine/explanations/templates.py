"""Deterministic explanations (P07-T06, docs/05 §11).

Every sentence carries citations (indexes into ``CandidateEvidence.claims`` or answer keys).
Strengths quote the evidence; gaps say plainly that missing evidence is *unknown*, not a
confirmed gap; conflicts say what differs and that a clarification is suggested. Nothing here
mentions protected characteristics (they never reach evaluation) or says "rejected".
"""

from __future__ import annotations

from collections.abc import Sequence

from ai_engine.contracts import (
    Contract,
    CriterionResult,
    CriterionSpec,
    EvidenceRef,
    EvidenceStatus,
)
from ai_engine.evaluation.engine import EvaluationResult

MAX_QUOTE = 120


class Sentence(Contract):
    kind: str  # strength | partial | gap | verify | conflict | answer
    criterion_id: str | None = None
    text: str
    citations: tuple[EvidenceRef, ...] = ()


class Explanation(Contract):
    sentences: tuple[Sentence, ...]
    dropped: int = 0  # sentences removed by the grounding validator

    def of_kind(self, kind: str) -> tuple[Sentence, ...]:
        return tuple(s for s in self.sentences if s.kind == kind)


def quote(ref: EvidenceRef) -> str:
    text = " ".join(ref.source.snippet.split())
    if len(text) > MAX_QUOTE:
        text = text[: MAX_QUOTE - 1].rstrip() + "…"
    return f"“{text}”"


def where(ref: EvidenceRef) -> str:
    if ref.question_key is not None:
        return "screening answer"
    return f"CV p.{ref.source.page}" if ref.source.page else "CV"


def _sentence_for(spec: CriterionSpec, result: CriterionResult) -> Sentence | None:
    first = result.evidence[0] if result.evidence else None
    name = spec.title
    if result.status == EvidenceStatus.CONFLICTING and first is not None:
        return Sentence(
            kind="conflict",
            criterion_id=spec.id,
            text=f"The CV and the answers differ on {name}; a clarification is suggested.",
            citations=result.evidence[:3],
        )
    if result.status == EvidenceStatus.NEEDS_VERIFICATION and first is not None:
        return Sentence(
            kind="verify",
            criterion_id=spec.id,
            text=f"{name}: {quote(first)} ({where(first)}) needs a person to verify it.",
            citations=(first,),
        )
    if not result.assessable or first is None:
        if spec.essential:
            return Sentence(
                kind="gap",
                criterion_id=spec.id,
                text=f"No evidence found for {name} — this is unknown, not a confirmed gap.",
            )
        return None
    score = result.score or 0
    inferred = result.status == EvidenceStatus.INFERRED
    if score >= 75:
        lead = "Likely evidence of" if inferred else "Evidence of"
        return Sentence(
            kind="strength",
            criterion_id=spec.id,
            text=f"{lead} {name}: {quote(first)} ({where(first)}).",
            citations=(first,),
        )
    if score >= 25:
        return Sentence(
            kind="partial",
            criterion_id=spec.id,
            text=f"Some evidence of {name}: {quote(first)} ({where(first)}).",
            citations=(first,),
        )
    return Sentence(
        kind="partial",
        criterion_id=spec.id,
        text=f"The evidence does not show {name}: {quote(first)} ({where(first)}).",
        citations=(first,),
    )


def build(result: EvaluationResult, specs: Sequence[CriterionSpec]) -> list[Sentence]:
    by_id = {r.criterion_id: r for r in result.criteria}
    order = {"strength": 0, "partial": 1, "verify": 2, "conflict": 3, "gap": 4}
    out = [s for spec in specs if (s := _sentence_for(spec, by_id[spec.id])) is not None]
    out.sort(key=lambda s: order.get(s.kind, 9))
    return out

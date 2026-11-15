"""Screening answers (P07-T04, docs/05 §8.1 "eligibility", EC-AI-05).

Each answered question is scored by its rubric mode:

* ``exact`` - matches the expected answer -> 100, otherwise 0 (an explicit answer is evidence);
* ``options`` - points of the chosen option(s), as a share of the best option;
* ``range`` - numeric answer inside ``[min, max]`` -> 100; or ``bands`` ``[{min, max, score}]``;
* ``rubric_text`` - share of the rubric's key phrases found in the text (low confidence: a person
  confirms);
* ``human`` - left for a person (``needs_verification``, not scored);
* ``none`` - recorded only.

Knock-out questions never decide anything: an answer that differs from the expected one sets
``eligibility_unmet`` so the application goes to the ``eligibility_review`` band for a human.
Unanswered questions are ``missing`` (unknown), never 0. Eligibility comes from answers only,
never from CV inference (docs/05 §8.1).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from ai_engine.contracts import (
    SCORE_BANDS,
    ClaimSource,
    Contract,
    EvidenceRef,
    EvidenceStatus,
)
from ai_engine.matching.rules import fold, mentions


class QuestionSpec(Contract):
    key: str
    type: str
    prompt: str = ""
    required: bool = False
    scoring: dict[str, Any] = Field(default_factory=dict)
    options: tuple[tuple[str, float | None], ...] = ()  # (value, points)
    is_knockout: bool = False
    knockout_expected: Any = None
    criterion_id: str | None = None

    @property
    def mode(self) -> str:
        return str(self.scoring.get("mode") or "none")


class AnswerInput(Contract):
    key: str
    value: Any = None
    response_id: str | None = None


class AnswerResult(Contract):
    key: str
    criterion_id: str | None = None
    status: EvidenceStatus
    score: int | None = None
    mode: str = "none"
    confidence: float = Field(default=0.0, ge=0, le=1)
    eligibility_unmet: bool = False
    evidence: tuple[EvidenceRef, ...] = ()
    reason: str = ""

    @property
    def assessable(self) -> bool:
        return self.score is not None


def snap(value: float) -> int:
    """Nearest rubric band (0/25/50/75/100)."""
    value = max(0.0, min(100.0, value))
    return min(SCORE_BANDS, key=lambda band: (abs(band - value), -band))


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _norm(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = fold(str(value))
    return {"true": "yes", "false": "no", "y": "yes", "n": "no"}.get(text, text)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _cite(question: QuestionSpec, answer: AnswerInput) -> tuple[EvidenceRef, ...]:
    shown = (
        answer.value if not isinstance(answer.value, list) else ", ".join(map(str, answer.value))
    )
    snippet = f"{question.prompt[:150]} -> {shown}"[:300] if question.prompt else str(shown)[:300]
    return (
        EvidenceRef(
            question_key=question.key,
            source=ClaimSource(
                snippet=snippet or "(answer)",
                question_response_id=answer.response_id or f"question:{question.key}",
            ),
        ),
    )


def knockout_unmet(question: QuestionSpec, answer: AnswerInput | None) -> bool:
    if not question.is_knockout or answer is None or _blank(answer.value):
        return False  # no answer: eligibility unknown, not unmet
    expected = question.knockout_expected
    if expected is None:
        return False
    if isinstance(expected, list):
        return _norm(answer.value) not in {_norm(e) for e in expected}
    return _norm(answer.value) != _norm(expected)


def score_answer(question: QuestionSpec, answer: AnswerInput | None) -> AnswerResult:
    if answer is None or _blank(answer.value):
        return AnswerResult(
            key=question.key,
            criterion_id=question.criterion_id,
            mode=question.mode,
            status=EvidenceStatus.MISSING,
            reason="unanswered",
        )
    cite = _cite(question, answer)
    unmet = knockout_unmet(question, answer)

    def result(
        status: EvidenceStatus, reason: str, score: int | None = None, confidence: float = 0.0
    ) -> AnswerResult:
        return AnswerResult(
            key=question.key,
            criterion_id=question.criterion_id,
            mode=question.mode,
            status=status,
            score=score,
            confidence=confidence,
            eligibility_unmet=unmet,
            evidence=cite,
            reason=reason,
        )

    reported = EvidenceStatus.CANDIDATE_REPORTED
    mode = question.mode
    scoring = question.scoring
    if mode == "exact":
        expected = scoring.get("expected")
        if expected is None:
            return result(reported, "no_expected")
        ok = (
            _norm(answer.value) in {_norm(e) for e in expected}
            if isinstance(expected, list)
            else _norm(answer.value) == _norm(expected)
        )
        return result(reported, "expected" if ok else "not_expected", 100 if ok else 0, 0.9)
    if mode == "options":
        points = {_norm(v): p for v, p in question.options if p is not None}
        best = max(points.values(), default=0.0)
        chosen = answer.value if isinstance(answer.value, list) else [answer.value]
        got = sum(points.get(_norm(v), 0.0) for v in chosen)
        if best <= 0:
            return result(reported, "no_points")
        multi = question.type == "multiple_choice"
        ceiling = sum(p for p in points.values() if p > 0) if multi else best
        return result(reported, "option_points", snap(100 * got / ceiling), 0.9)
    if mode == "range":
        number = _number(answer.value)
        if number is None:
            return result(EvidenceStatus.NEEDS_VERIFICATION, "not_a_number")
        for band in scoring.get("bands") or []:
            lo, hi = band.get("min"), band.get("max")
            if (lo is None or number >= lo) and (hi is None or number <= hi):
                return result(reported, "band", snap(float(band.get("score", 0))), 0.9)
        lo, hi = scoring.get("min"), scoring.get("max")
        inside = (lo is None or number >= lo) and (hi is None or number <= hi)
        return result(
            reported, "in_range" if inside else "out_of_range", 100 if inside else 25, 0.9
        )
    if mode == "rubric_text":
        phrases = [str(k) for k in scoring.get("keywords") or scoring.get("criteria") or []]
        text = " ".join(answer.value) if isinstance(answer.value, list) else str(answer.value)
        if not phrases:
            return result(EvidenceStatus.NEEDS_VERIFICATION, "human")
        found = sum(1 for phrase in phrases if mentions(text, [phrase]))
        # keyword rubric: a person should read the answer, hence low confidence
        return result(
            reported, f"keywords={found}/{len(phrases)}", snap(100 * found / len(phrases)), 0.5
        )
    if mode == "human":
        return result(EvidenceStatus.NEEDS_VERIFICATION, "scored_by_a_person")
    return result(reported, "not_scored")


def score_answers(questions: list[QuestionSpec], answers: list[AnswerInput]) -> list[AnswerResult]:
    by_key = {a.key: a for a in answers}
    return [score_answer(q, by_key.get(q.key)) for q in questions]

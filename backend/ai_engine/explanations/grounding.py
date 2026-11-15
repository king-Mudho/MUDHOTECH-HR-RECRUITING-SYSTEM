"""Grounding validator (P07-T06, docs/05 §9.5 and §11).

A sentence survives only when it is supported:

* sentences asserting evidence (strength / partial / verify / conflict / answer) need at least
  one citation, every citation must resolve (a claim index that exists, or an answered question)
  and its snippet must match the cited source; any quoted text must come from a cited snippet;
* gap sentences assert *absence*: they are valid only when the criterion really has no evidence.

Ungrounded sentences are dropped and counted; the target grounding rate is 100 %. The same
validator checks LLM-phrased summaries (P07-T07) before anything is shown.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from ai_engine.contracts import (
    CandidateEvidence,
    CriterionResult,
    CriterionSpec,
    EvidenceRef,
    EvidenceStatus,
)
from ai_engine.evaluation.engine import EvaluationResult
from ai_engine.explanations.templates import Explanation, Sentence, build
from ai_engine.matching.answers import AnswerResult

_QUOTED = re.compile(r"“([^”]*)”|\"([^\"]*)\"")


def _norm(text: str) -> str:
    return " ".join(text.replace("…", "").split()).lower()


def citation_valid(
    ref: EvidenceRef, evidence: CandidateEvidence, answers: dict[str, AnswerResult]
) -> bool:
    if ref.claim_index is not None:
        if ref.claim_index >= len(evidence.claims):
            return False
        return _norm(evidence.claims[ref.claim_index].source.snippet) == _norm(ref.source.snippet)
    if ref.question_key is not None:
        answer = answers.get(ref.question_key)
        return answer is not None and answer.status != EvidenceStatus.MISSING
    return False


def sentence_grounded(
    sentence: Sentence,
    evidence: CandidateEvidence,
    results: dict[str, CriterionResult],
    answers: dict[str, AnswerResult],
) -> bool:
    if sentence.kind == "gap":
        result = results.get(sentence.criterion_id or "")
        return (
            result is not None and result.status == EvidenceStatus.MISSING and not result.evidence
        )
    if not sentence.citations:
        return False
    if not all(citation_valid(c, evidence, answers) for c in sentence.citations):
        return False
    snippets = [_norm(c.source.snippet) for c in sentence.citations]
    for match in _QUOTED.finditer(sentence.text):
        quoted = _norm(match.group(1) or match.group(2) or "")
        if quoted and not any(quoted in s for s in snippets):
            return False
    return True


def validate(
    sentences: Iterable[Sentence],
    evidence: CandidateEvidence,
    results: Sequence[CriterionResult],
    answers: Sequence[AnswerResult],
) -> Explanation:
    by_id = {r.criterion_id: r for r in results}
    by_key = {a.key: a for a in answers}
    kept, dropped = [], 0
    for sentence in sentences:
        if sentence_grounded(sentence, evidence, by_id, by_key):
            kept.append(sentence)
        else:
            dropped += 1
    return Explanation(sentences=tuple(kept), dropped=dropped)


def grounding_rate(explanation: Explanation) -> float:
    total = len(explanation.sentences) + explanation.dropped
    return 1.0 if total == 0 else len(explanation.sentences) / total


def explain(
    result: EvaluationResult, specs: Sequence[CriterionSpec], evidence: CandidateEvidence
) -> Explanation:
    """Template sentences for an evaluation, kept only when grounded."""
    return validate(build(result, specs), evidence, result.criteria, result.answers)

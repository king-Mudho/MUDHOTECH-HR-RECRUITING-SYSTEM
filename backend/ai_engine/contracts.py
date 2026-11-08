"""Pydantic contracts exchanged between the AI engine and its Django adapters.

Phase 01 placeholder: the shared base model and evidence-status vocabulary. Full contracts
(DocumentText, ExtractedClaim, CandidateEvidence, Criterion, CriterionResult, Evaluation) are
implemented in P06-T02 / Phase 07 per docs/05.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Immutable, strict base for every engine contract."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class EvidenceStatus(StrEnum):
    """Principle 2 (evidence-first) + 3 (missing != negative)."""

    FOUND = "found"
    MISSING = "missing"
    INFERRED = "inferred"
    CONFLICTING = "conflicting"
    HUMAN_VERIFIED = "human_verified"


class SourceRef(Contract):
    """Where a claim came from: a document page/snippet or a questionnaire response."""

    document_id: str | None = None
    page: int | None = None
    snippet: str | None = None
    question_response_id: str | None = None

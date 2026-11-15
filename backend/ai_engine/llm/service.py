"""Guarded LLM use (P07-T07, docs/05 §9, EC-AI-06/07).

Guardrails, in order:
1. off unless enabled (platform flag AND organisation ``llm_enabled``); skipped when the CV is
   suspected of prompt injection;
2. redaction: candidate names -> [CANDIDATE], emails/phones/IDs/protected values removed;
3. data/instruction separation: untrusted text only inside ``<data>`` with a system prompt that
   says so; prompts are versioned files (``prompts/*.md``) identified by their hash;
4. structured output: strict JSON parsed into pydantic models (extra keys rejected); 2 retries,
   then the deterministic path;
5. grounding: every summary sentence must cite evidence ids that exist and share words with the
   cited evidence; skills suggested for a section are kept only when the section text contains
   them verbatim;
6. determinism: responses cached by (prompt hash, input hash, model); a circuit breaker stops
   calling a failing provider for a while.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from ai_engine.contracts import (
    CandidateEvidence,
    ClaimEvidence,
    ClaimSource,
    Contract,
    CriterionSpec,
    ExtractedClaim,
    ExtractionMethod,
    Flag,
    SkillData,
)
from ai_engine.evaluation.engine import EvaluationResult
from ai_engine.explanations.templates import Explanation, Sentence
from ai_engine.extraction.pii import redact_for_llm
from ai_engine.extraction.skills import SkillIndex
from ai_engine.llm.base import LLMError, LLMUnavailableError, NullProvider, Provider
from ai_engine.matching.experience_match import keywords
from ai_engine.matching.rules import mentions
from ai_engine.security.injection import find_injections, is_suspected
from ai_engine.versioning import input_hash

PROMPTS = Path(__file__).resolve().parent / "prompts"
MAX_ATTEMPTS = 3  # first try + 2 retries


def load_prompt(name: str) -> tuple[str, str]:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


class _SummarySentence(Contract):
    text: str = Field(min_length=1, max_length=400)
    citations: list[str] = Field(min_length=1, max_length=5)


class SummaryOutput(Contract):
    sentences: list[_SummarySentence] = Field(max_length=5)


class SectionOutput(Contract):
    skills: list[str] = Field(max_length=30)


class CircuitBreaker:
    def __init__(self, failures: int = 3, cooldown: float = 300.0) -> None:
        self.failures = failures
        self.cooldown = cooldown
        self._count = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._opened_at, self._count = None, 0  # half-open: try again
                return True
            return False

    def success(self) -> None:
        with self._lock:
            self._count, self._opened_at = 0, None

    def failure(self) -> None:
        with self._lock:
            self._count += 1
            if self._count >= self.failures:
                self._opened_at = time.monotonic()


def _json(text: str) -> Any:
    """The first JSON object in the reply (models sometimes wrap it in a code fence)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object")
    return json.loads(match.group(0))


class LLMService:
    def __init__(
        self,
        provider: Provider | None = None,
        *,
        enabled: bool = False,
        cache: Any = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.provider: Provider = provider or NullProvider()
        self.enabled = enabled and self.provider.name != "null"
        self.cache = cache  # get/set mapping-like (Django cache in production)
        self.breaker = breaker or CircuitBreaker()
        self.calls = 0

    # ------------------------------------------------------------------ plumbing
    def _ask(self, prompt_name: str, data: str, schema: type[Contract]) -> Contract:
        if not self.enabled:
            raise LLMUnavailableError("LLM disabled")
        if not self.breaker.allow():
            raise LLMUnavailableError("circuit open")
        system, prompt_hash = load_prompt(prompt_name)
        key = f"llm:{prompt_hash}:{input_hash({'data': data})}:{self.provider.model}"
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached:
                return schema.model_validate_json(cached)
        user = f"<data>\n{data}\n</data>"
        last: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            self.calls += 1
            try:
                reply = self.provider.complete(system, user)
                parsed = schema.model_validate(_json(reply.text))
            except LLMUnavailableError:
                raise
            except (LLMError, ValueError, ValidationError) as exc:
                last = exc
                continue
            self.breaker.success()
            if self.cache is not None:
                self.cache.set(key, parsed.model_dump_json(), 30 * 24 * 3600)
            return parsed
        self.breaker.failure()
        raise LLMError(f"no valid answer after {MAX_ATTEMPTS} attempts") from last

    @staticmethod
    def _injected(evidence: CandidateEvidence, text: str = "") -> bool:
        return Flag.INJECTION_SUSPECTED in evidence.flags or is_suspected(find_injections(text))

    # ------------------------------------------------------------------- summary
    def summarise(
        self,
        result: EvaluationResult,
        explanation: Explanation,
        specs: Sequence[CriterionSpec],
        evidence: CandidateEvidence,
        *,
        names: Sequence[str] = (),
    ) -> Explanation | None:
        """LLM phrasing of the grounded template sentences, or None (use the templates)."""
        if not self.enabled or self._injected(evidence) or not explanation.sentences:
            return None
        ids: dict[str, Sentence] = {f"E{i + 1}": s for i, s in enumerate(explanation.sentences)}
        titles = {s.id: s.title for s in specs}
        lines = [
            f"{eid}: [{s.kind}] {titles.get(s.criterion_id or '', '')}: "
            f"{redact_for_llm(s.text, names=list(names))}"
            for eid, s in ids.items()
        ]
        data = "\n".join([f"band: {result.band}", f"coverage: {result.coverage:.2f}", *lines])
        try:
            out = self._ask("summary_v1", data, SummaryOutput)
        except LLMError:
            return None
        if not isinstance(out, SummaryOutput):  # _ask returns the requested schema
            return None
        kept: list[Sentence] = []
        dropped = 0
        for sentence in out.sentences:
            cited = [ids[c] for c in sentence.citations if c in ids]
            if len(cited) != len(sentence.citations) or not cited:
                dropped += 1  # invented or missing evidence id
                continue
            support = set().union(
                *(keywords(f"{c.text} {titles.get(c.criterion_id or '', '')}") for c in cited)
            )
            if not keywords(sentence.text) & support or self._unsafe(sentence.text):
                dropped += 1
                continue
            kept.append(
                Sentence(
                    kind="summary",
                    criterion_id=cited[0].criterion_id,
                    text=sentence.text,
                    citations=tuple(ref for c in cited for ref in c.citations),
                )
            )
        if not kept:
            return None
        return Explanation(sentences=tuple(kept), dropped=dropped)

    @staticmethod
    def _unsafe(text: str) -> bool:
        lowered = text.lower()
        banned = ("reject", "/100", "score of", "hire immediately", "religio", "gender", "tribe")
        return any(b in lowered for b in banned) or is_suspected(find_injections(text))

    # ------------------------------------------------------------- section assist
    def assist_section(
        self,
        section_text: str,
        *,
        page: int,
        char_start: int,
        document_id: str,
        index: SkillIndex,
        existing: Mapping[str, Any] | None = None,
    ) -> list[ExtractedClaim]:
        """Skills for a low-confidence section; only those written verbatim in the text."""
        if not self.enabled or is_suspected(find_injections(section_text)):
            return []
        try:
            out = self._ask("section_assist_v1", redact_for_llm(section_text), SectionOutput)
        except LLMError:
            return []
        if not isinstance(out, SectionOutput):
            return []
        claims = []
        for raw in out.skills:
            raw = raw.strip()
            position = section_text.lower().find(raw.lower())
            if not raw or position < 0 or not mentions(section_text, [raw]):
                continue  # not in the text: hallucinated or paraphrased
            entry = index.lookup(raw)
            if existing is not None and entry is not None and entry.skill_id in existing:
                continue
            claims.append(
                ExtractedClaim(
                    data=SkillData(
                        raw=section_text[position : position + len(raw)],
                        skill_id=entry.skill_id if entry else None,
                        canonical=entry.canonical if entry else None,
                    ),
                    source=ClaimSource(
                        snippet=section_text[position : position + len(raw)][:300],
                        document_id=document_id,
                        page=page,
                        char_start=char_start + position,
                        char_end=char_start + position + len(raw),
                    ),
                    method=ExtractionMethod.LLM,
                    confidence=0.5,
                    evidence=ClaimEvidence.EXPLICIT,
                )
            )
        return claims

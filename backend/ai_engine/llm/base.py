"""LLM provider interface (P07-T07, docs/05 §9).

The LLM is optional and off by default (platform flag AND organisation ``llm_enabled``). It may
only (a) re-phrase a summary of results the deterministic engine already computed and (b) suggest
skills for a low-confidence CV section - suggestions are kept only when the text literally
contains them. It never scores, ranks, decides eligibility or sees excluded/protected data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """Any LLM failure. Callers fall back to the deterministic path (EC-AI-06/07)."""


class LLMUnavailableError(LLMError):
    """Disabled, not configured, SDK missing, or circuit open."""


class LLMRefusedError(LLMError):
    """The model declined (``stop_reason == "refusal"``)."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    stop_reason: str = "end_turn"


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int = 2000) -> LLMResponse:
        """One request; raise ``LLMError`` subclasses on failure."""
        ...


class NullProvider:
    """The default: no LLM. Every call is unavailable, so the deterministic path is used."""

    name = "null"
    model = "none"

    def complete(self, system: str, user: str, *, max_tokens: int = 2000) -> LLMResponse:
        raise LLMUnavailableError("LLM disabled")

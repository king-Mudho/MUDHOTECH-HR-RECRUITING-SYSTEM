"""Anthropic Claude adapter (official ``anthropic`` SDK, optional ``llm`` extra).

Model ``claude-opus-5-5`` by default (``LLM_MODEL`` overrides). Thinking is always on for this
model and sampling parameters are not accepted, so determinism comes from the response cache
keyed by (prompt hash, input hash, model), not from ``temperature``. Effort is ``low``: the task
is short re-phrasing. A refusal raises ``LLMRefusedError``; the caller then uses the deterministic
template text (our fallback), so no server-side model fallback is configured.
"""

from __future__ import annotations

from typing import Any

from ai_engine.llm.base import LLMError, LLMRefusedError, LLMResponse, LLMUnavailableError

DEFAULT_MODEL = "claude-opus-5-5"
TIMEOUT_SECONDS = 30.0


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = "low",
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self._client = client
        self._api_key = api_key

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - optional extra
                raise LLMUnavailableError("anthropic SDK not installed (llm extra)") from exc
            # retries are ours (bounded, with the circuit breaker); the SDK must not add more
            self._client = anthropic.Anthropic(
                api_key=self._api_key, timeout=TIMEOUT_SECONDS, max_retries=0
            )
        return self._client

    def complete(self, system: str, user: str, *, max_tokens: int = 2000) -> LLMResponse:
        client = self._get_client()
        try:
            import anthropic

            api_error: tuple[type[BaseException], ...] = (anthropic.APIError,)
        except ImportError:  # pragma: no cover - a test double was injected
            api_error = ()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort},
            )
        except api_error as exc:
            raise LLMError(f"anthropic: {type(exc).__name__}") from exc
        if getattr(response, "stop_reason", None) == "refusal":
            raise LLMRefusedError("model declined")
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return LLMResponse(text=text, model=self.model, stop_reason=str(response.stop_reason))

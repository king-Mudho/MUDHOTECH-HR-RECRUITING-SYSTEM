"""OpenAI adapter (optional; the ``openai`` SDK is not a project dependency - install it only
where an organisation has chosen this provider). Same contract as the Anthropic adapter."""

from __future__ import annotations

from typing import Any

from ai_engine.llm.base import LLMError, LLMResponse, LLMUnavailableError


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, *, model: str, client: Any = None) -> None:
        self.model = model
        self._client = client
        self._api_key = api_key

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - optional
                raise LLMUnavailableError("openai SDK not installed") from exc
            self._client = openai.OpenAI(api_key=self._api_key, timeout=30.0, max_retries=0)
        return self._client

    def complete(self, system: str, user: str, *, max_tokens: int = 2000) -> LLMResponse:
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:  # the SDK's error hierarchy is not imported here
            raise LLMError(f"openai: {type(exc).__name__}") from exc
        choice = response.choices[0]
        return LLMResponse(
            text=choice.message.content or "",
            model=self.model,
            stop_reason=str(choice.finish_reason),
        )

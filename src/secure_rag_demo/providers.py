from typing import Protocol

from openai import OpenAI, OpenAIError

from secure_rag_demo.config import Settings


class ProviderError(Exception):
    """Model provider unavailable or timed out. Message is never shown to clients."""


class ChatProvider(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class OpenAICompatibleProvider:
    """Any OpenAI-compatible endpoint. Defaults to local Ollama via LLM_BASE_URL."""

    def __init__(self, settings: Settings, timeout: float = 60.0) -> None:
        self._model = settings.llm_model
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=timeout,
            max_retries=0,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except OpenAIError as exc:
            raise ProviderError("provider call failed") from exc
        return response.choices[0].message.content or ""

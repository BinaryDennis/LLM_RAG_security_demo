from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI, OpenAIError
from openai.types.chat import ChatCompletionToolParam

from secure_rag_demo.config import Settings


class ProviderError(Exception):
    """Model provider unavailable or timed out. Message is never shown to clients."""


class ChatProvider(Protocol):
    def complete(
        self, system_prompt: str, user_prompt: str, timeout: float | None = None
    ) -> str: ...


@dataclass(frozen=True)
class AgentToolCall:
    name: str
    arguments: str


class OpenAICompatibleProvider:
    """Any OpenAI-compatible endpoint. Defaults to local Ollama via LLM_BASE_URL."""

    def __init__(self, settings: Settings, timeout: float = 60.0) -> None:
        self._model = settings.llm_model
        self._timeout = timeout
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=timeout,
            max_retries=0,
        )

    def complete(self, system_prompt: str, user_prompt: str, timeout: float | None = None) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                timeout=timeout if timeout is not None else self._timeout,
            )
        except OpenAIError as exc:
            raise ProviderError("provider call failed") from exc
        return response.choices[0].message.content or ""

    def request_tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        tool: ChatCompletionToolParam,
        timeout: float,
    ) -> list[AgentToolCall]:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[tool],
                tool_choice="required",
                timeout=timeout,
            )
        except OpenAIError as exc:
            raise ProviderError("provider call failed") from exc
        tool_calls = response.choices[0].message.tool_calls or []
        parsed_calls: list[AgentToolCall] = []
        for tool_call in tool_calls:
            if tool_call.type != "function":
                raise ProviderError("unsupported tool call")
            parsed_calls.append(
                AgentToolCall(
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )
        return parsed_calls

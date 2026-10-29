import json
import time
from dataclasses import dataclass
from typing import Protocol

from openai.types.chat import ChatCompletionToolParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from secure_rag_demo.answering import answer_question
from secure_rag_demo.auth import Principal
from secure_rag_demo.embeddings import EmbeddingService
from secure_rag_demo.providers import AgentToolCall
from secure_rag_demo.retrieval import search_chunks
from secure_rag_demo.schemas import Citation

AGENT_TIMEOUT_SECONDS = 30.0
SEARCH_TOOL_NAME = "search_documents"
TOOL_ALLOWLIST = frozenset({SEARCH_TOOL_NAME})
SEARCH_TOOL: ChatCompletionToolParam = {
    "type": "function",
    "function": {
        "name": SEARCH_TOOL_NAME,
        "description": "Search the read-only knowledge base for evidence relevant to a question.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "maxLength": 2000}},
            "required": ["question"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

_SYSTEM_PROMPT = (
    "You are a constrained retrieval router. Call the single available search tool exactly once "
    "with the user's question. Do not answer, invent another tool, or request actions outside "
    "that search."
)


class AgentError(Exception):
    """The constrained agent could not complete its one permitted operation."""


class AgentToolError(AgentError):
    """The model requested a tool or arguments outside the explicit allowlist."""


class AgentTimeout(AgentError):
    """The agent exceeded its request deadline."""


class AgentProvider(Protocol):
    def request_tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        tool: ChatCompletionToolParam,
        timeout: float,
    ) -> list[AgentToolCall]: ...

    def complete(
        self, system_prompt: str, user_prompt: str, timeout: float | None = None
    ) -> str: ...


class _SearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=2000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


@dataclass(frozen=True)
class AgentAnswer:
    answer: str | None
    citations: list[Citation]
    abstained: bool


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AgentTimeout("agent request timed out")
    return remaining


def run_read_only_agent(
    question: str,
    principal: Principal,
    session: Session,
    embedder: EmbeddingService,
    provider: AgentProvider,
    *,
    timeout_seconds: float = AGENT_TIMEOUT_SECONDS,
) -> AgentAnswer:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    deadline = time.monotonic() + timeout_seconds
    try:
        tool_calls = provider.request_tool_call(
            _SYSTEM_PROMPT,
            question,
            SEARCH_TOOL,
            _remaining(deadline),
        )
    except TimeoutError as exc:
        raise AgentTimeout("agent request timed out") from exc

    if len(tool_calls) != 1:
        raise AgentToolError("agent must request exactly one tool")
    tool_call = tool_calls[0]
    if tool_call.name not in TOOL_ALLOWLIST:
        raise AgentToolError("requested tool is not allowed")
    if len(tool_call.arguments) > 10_000:
        raise AgentToolError("tool arguments are too large")
    try:
        arguments = _SearchArguments.model_validate(json.loads(tool_call.arguments))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AgentToolError("tool arguments are invalid") from exc

    _remaining(deadline)
    embedding = embedder.embed_query(arguments.question)
    remaining = _remaining(deadline)
    session.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": f"{max(1, int(remaining * 1000))}ms"},
    )
    chunks = search_chunks(session, embedding, principal)
    _remaining(deadline)
    answer, citations, abstained = answer_question(
        question,
        chunks,
        provider,
        timeout=_remaining(deadline),
    )
    _remaining(deadline)
    return AgentAnswer(answer=answer, citations=citations, abstained=abstained)

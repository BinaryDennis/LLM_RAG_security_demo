import logging
import uuid
from typing import Any, Protocol

from secure_rag_demo.auth import Principal
from secure_rag_demo.config import Settings

logger = logging.getLogger(__name__)


class TraceSink(Protocol):
    def send(self, payload: dict[str, Any]) -> None: ...


class LangSmithSink:
    """Sends metadata-only runs to LangSmith. Content is never part of the payload."""

    def __init__(self) -> None:
        from langsmith import Client

        self._client = Client(hide_inputs=True, hide_outputs=True)

    def send(self, payload: dict[str, Any]) -> None:
        self._client.create_run(
            name="rag_query",
            run_type="chain",
            inputs={},
            outputs={},
            extra={"metadata": payload},
        )


def build_sink(settings: Settings) -> TraceSink | None:
    """Tracing is off unless LANGSMITH_TRACING=true."""
    if not settings.langsmith_tracing:
        return None
    return LangSmithSink()


def trace_query(
    sink: TraceSink | None,
    request_id: uuid.UUID,
    principal: Principal,
    retrieved_count: int,
    model_name: str,
    outcome: str,
    duration_ms: float = 0.0,
) -> None:
    """Record metadata only. Never pass the question, prompt, chunk text or answer."""
    if sink is None:
        return
    payload = {
        "request_id": str(request_id),
        "principal": principal.subject,
        "retrieved_count": retrieved_count,
        "model": model_name,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 1),
    }
    try:
        sink.send(payload)
    except Exception:  # noqa: BLE001 - telemetry must never break a query
        logger.warning("trace export failed")

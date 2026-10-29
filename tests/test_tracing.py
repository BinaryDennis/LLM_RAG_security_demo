import json
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from secure_rag_demo import api
from secure_rag_demo.auth import Principal
from secure_rag_demo.config import Settings
from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.schemas import DocumentInput
from secure_rag_demo.tracing import build_sink, trace_query
from tests.conftest import FakeEmbedder

Q = "PRIVATE_QUESTION_7f21"
CHUNK = "PRIVATE_CHUNK_9a34"
ANSWER = "PRIVATE_ANSWER_2c18"
PRINCIPAL = Principal("demo-public", frozenset({"public"}))


class FakeSink:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class ExplodingSink:
    def send(self, payload: dict[str, Any]) -> None:
        raise RuntimeError("network down")


class AnswerProvider:
    def complete(self, system_prompt: str, user_prompt: str, timeout: float | None = None) -> str:
        return ANSWER


def test_trace_has_metadata_fields() -> None:
    sink = FakeSink()
    rid = uuid.uuid4()
    trace_query(sink, rid, PRINCIPAL, 3, "m", "answered", 12.34)
    assert sink.payloads == [
        {
            "request_id": str(rid),
            "principal": "demo-public",
            "retrieved_count": 3,
            "model": "m",
            "outcome": "answered",
            "duration_ms": 12.3,
        }
    ]


def test_trace_failure_does_not_raise() -> None:
    trace_query(ExplodingSink(), uuid.uuid4(), PRINCIPAL, 0, "m", "abstained")


def test_tracing_disabled_by_default() -> None:
    assert Settings().langsmith_tracing is False
    assert Settings().langsmith_hide_inputs is True
    assert Settings().langsmith_hide_outputs is True
    assert build_sink(Settings(langsmith_tracing=False)) is None


def test_langsmith_client_receives_hide_settings() -> None:
    from unittest.mock import patch

    with patch("langsmith.Client") as client:
        build_sink(Settings(langsmith_tracing=True))
    client.assert_called_once_with(hide_inputs=True, hide_outputs=True)


def test_private_strings_never_reach_traces(session: Session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(demo_token_public="tok", demo_token_restricted="tok2")
    monkeypatch.setattr("secure_rag_demo.auth.get_settings", lambda: settings)
    ingest_document(
        session,
        DocumentInput(
            title="t", source_url="https://e.se", version="1", visibility="public", text=CHUNK
        ),
        FakeEmbedder(),
    )
    sink = FakeSink()
    app = api.create_app()

    def _session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[api.get_session] = _session
    app.dependency_overrides[api.get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[api.get_provider] = lambda: AnswerProvider()
    app.dependency_overrides[api.get_trace_sink] = lambda: sink

    r = TestClient(app).post(
        "/v1/query", json={"question": Q}, headers={"Authorization": "Bearer tok"}
    )
    assert r.status_code == 200 and ANSWER in r.text
    assert len(sink.payloads) == 1
    serialized = json.dumps(sink.payloads)
    for secret in (Q, CHUNK, ANSWER):
        assert secret not in serialized

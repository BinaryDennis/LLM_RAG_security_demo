import socket
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from secure_rag_demo import agent, api
from secure_rag_demo.auth import Principal
from secure_rag_demo.config import Settings
from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.models import Document
from secure_rag_demo.providers import AgentToolCall
from secure_rag_demo.retrieval import RetrievedChunk
from secure_rag_demo.schemas import DocumentInput
from tests.conftest import FakeEmbedder

PUBLIC = Principal("demo-public", frozenset({"public"}))
SETTINGS = Settings(demo_token_public="tok-public", demo_token_restricted="tok-restricted")


class FakeAgentProvider:
    def __init__(
        self,
        tool_calls: list[AgentToolCall] | None = None,
        delay: float = 0,
        completion_delay: float = 0,
    ) -> None:
        self.tool_calls = tool_calls or [
            AgentToolCall(
                name=agent.SEARCH_TOOL_NAME,
                arguments='{"question":"Lösenord?"}',
            )
        ]
        self.delay = delay
        self.completion_delay = completion_delay
        self.tools: list[dict[str, object]] = []
        self.timeouts: list[float] = []
        self.completions = 0

    def request_tool_call(
        self,
        system_prompt: str,
        user_prompt: str,
        tool: dict[str, object],
        timeout: float,
    ) -> list[AgentToolCall]:
        self.tools.append(tool)
        self.timeouts.append(timeout)
        time.sleep(self.delay)
        return self.tool_calls

    def complete(self, system_prompt: str, user_prompt: str, timeout: float | None = None) -> str:
        self.completions += 1
        time.sleep(self.completion_delay)
        if timeout is not None:
            self.timeouts.append(timeout)
        return "Svar från källan."


def seed(session: Session, visibility: str, text: str) -> None:
    ingest_document(
        session,
        DocumentInput(
            title=f"{visibility} doc",
            source_url="https://example.se/x",
            version="1",
            visibility=visibility,
            text=text,
        ),
        FakeEmbedder(),
    )


@pytest.fixture
def client(session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr("secure_rag_demo.auth.get_settings", lambda: SETTINGS)
    app = api.create_app()

    def get_test_session():
        yield session

    app.dependency_overrides[api.get_session] = get_test_session
    app.dependency_overrides[api.get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[api.get_provider] = lambda: FakeAgentProvider()
    return TestClient(app)


def test_agent_uses_its_only_tool_once_and_does_not_write(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(session, "public", "Lösenord ska vara långa och unika.")
    before = session.scalar(select(func.count()).select_from(Document))
    provider = FakeAgentProvider()
    retrieval_calls = 0
    original_search = agent.search_chunks

    def count_retrievals(
        db: Session, embedding: list[float], principal: Principal
    ) -> list[RetrievedChunk]:
        nonlocal retrieval_calls
        retrieval_calls += 1
        return original_search(db, embedding, principal)

    monkeypatch.setattr(agent, "search_chunks", count_retrievals)

    result = agent.run_read_only_agent("Lösenord?", PUBLIC, session, FakeEmbedder(), provider)

    after = session.scalar(select(func.count()).select_from(Document))
    assert result.abstained is False
    assert result.answer == "Svar från källan."
    assert len(result.citations) == 1
    assert before == after
    assert retrieval_calls == 1
    assert len(provider.tools) == 1
    assert provider.tools[0]["function"]["name"] == agent.SEARCH_TOOL_NAME
    assert agent.TOOL_ALLOWLIST == frozenset({agent.SEARCH_TOOL_NAME})


def test_agent_rejects_non_allowlisted_tool_without_retrieval(session: Session) -> None:
    provider = FakeAgentProvider(
        [AgentToolCall(name="fetch_url", arguments='{"url":"https://example.invalid"}')]
    )

    with pytest.raises(agent.AgentToolError, match="not allowed"):
        agent.run_read_only_agent("Lösenord?", PUBLIC, session, FakeEmbedder(), provider)

    assert provider.completions == 0


def test_agent_rejects_multiple_tool_calls(session: Session) -> None:
    provider = FakeAgentProvider(
        [
            AgentToolCall(name=agent.SEARCH_TOOL_NAME, arguments='{"question":"one"}'),
            AgentToolCall(name=agent.SEARCH_TOOL_NAME, arguments='{"question":"two"}'),
        ]
    )

    with pytest.raises(agent.AgentToolError, match="exactly one"):
        agent.run_read_only_agent("Lösenord?", PUBLIC, session, FakeEmbedder(), provider)

    assert provider.completions == 0


def test_agent_rejects_oversized_tool_arguments(session: Session) -> None:
    provider = FakeAgentProvider(
        [AgentToolCall(name=agent.SEARCH_TOOL_NAME, arguments=" " * 10_001)]
    )

    with pytest.raises(agent.AgentToolError, match="too large"):
        agent.run_read_only_agent("Lösenord?", PUBLIC, session, FakeEmbedder(), provider)

    assert provider.completions == 0


def test_agent_retrieval_obeys_server_role(session: Session) -> None:
    seed(session, "restricted_demo", "hemligtest")
    provider = FakeAgentProvider(
        [AgentToolCall(name=agent.SEARCH_TOOL_NAME, arguments='{"question":"hemligtest"}')]
    )

    result = agent.run_read_only_agent("hemligtest", PUBLIC, session, FakeEmbedder(), provider)

    assert result.abstained is True
    assert result.answer is None
    assert result.citations == []
    assert provider.completions == 0


def test_agent_enforces_execution_deadline(session: Session) -> None:
    provider = FakeAgentProvider(delay=0.02)

    with pytest.raises(agent.AgentTimeout):
        agent.run_read_only_agent(
            "Lösenord?", PUBLIC, session, FakeEmbedder(), provider, timeout_seconds=0.001
        )

    assert provider.completions == 0


def test_agent_enforces_deadline_during_final_answer(session: Session) -> None:
    seed(session, "public", "Lösenord ska vara långa och unika.")
    provider = FakeAgentProvider(completion_delay=0.55)

    with pytest.raises(agent.AgentTimeout):
        agent.run_read_only_agent(
            "Lösenord?", PUBLIC, session, FakeEmbedder(), provider, timeout_seconds=0.5
        )

    assert provider.completions == 1


def test_agent_tool_schema_has_no_network_or_write_capability() -> None:
    tool = agent.SEARCH_TOOL
    assert tool["function"]["name"] == agent.SEARCH_TOOL_NAME
    assert "url" not in str(tool).lower()
    assert "delete" not in str(tool).lower()
    assert "write" not in str(tool).lower()


def test_agent_tool_path_makes_no_network_requests(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(session, "public", "Lösenord ska vara långa och unika.")

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("agent tool path attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    result = agent.run_read_only_agent(
        "Lösenord?", PUBLIC, session, FakeEmbedder(), FakeAgentProvider()
    )

    assert result.abstained is False


def test_agent_endpoint_requires_auth_and_returns_grounded_answer(
    session: Session, client: TestClient
) -> None:
    seed(session, "public", "Lösenord ska vara långa och unika.")

    response = client.post(
        "/v1/agent-query",
        json={"question": "Lösenord?"},
        headers={"Authorization": "Bearer tok-public"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Svar från källan."
    assert response.json()["abstained"] is False
    assert len(response.json()["citations"]) == 1


def test_agent_endpoint_does_not_expose_restricted_documents(
    session: Session, client: TestClient
) -> None:
    seed(session, "restricted_demo", "hemligtest")
    response = client.post(
        "/v1/agent-query",
        json={"question": "hemligtest"},
        headers={"Authorization": "Bearer tok-public"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] is None
    assert response.json()["citations"] == []
    assert response.json()["abstained"] is True


def test_agent_endpoint_rejects_missing_auth(client: TestClient) -> None:
    response = client.post("/v1/agent-query", json={"question": "Lösenord?"})
    assert response.status_code == 401

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from secure_rag_demo import api
from secure_rag_demo.auth import Principal
from secure_rag_demo.config import Settings
from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.models import DocumentChunk
from secure_rag_demo.providers import ProviderError
from secure_rag_demo.schemas import DocumentInput
from tests.conftest import FakeEmbedder
from tests.test_answering import FakeProvider

SETTINGS = Settings(demo_token_public="tok-public", demo_token_restricted="tok-restricted")
PUBLIC = {"Authorization": "Bearer tok-public"}


class BoomProvider:
    def complete(self, system_prompt: str, user_prompt: str, timeout: float | None = None) -> str:
        raise ProviderError("secret internal detail")


class BrokenSession:
    def execute(self, *args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT secret_table", {}, Exception("db password leaked"))


@pytest.fixture
def client_factory(session: Session, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(api, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr("secure_rag_demo.auth.get_settings", lambda: SETTINGS)
    created: list[TestClient] = []

    def make(provider: object = None, db: object = None) -> TestClient:
        app = api.create_app()

        def _session() -> Iterator[object]:
            yield db if db is not None else session

        app.dependency_overrides[api.get_session] = _session
        app.dependency_overrides[api.get_embedder] = lambda: FakeEmbedder()
        app.dependency_overrides[api.get_provider] = lambda: provider or FakeProvider()
        c = TestClient(app)
        created.append(c)
        return c

    return make


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


def test_supported_question_returns_citations(session: Session, client_factory) -> None:  # type: ignore[no-untyped-def]
    seed(session, "public", "Lösenord ska vara långa och unika.")
    body = client_factory().post("/v1/query", json={"question": "Lösenord?"}, headers=PUBLIC).json()
    assert body["abstained"] is False
    assert body["answer"] == "Svar från källan."
    retrieved = {str(c.id) for c in session.query(DocumentChunk)}
    assert body["citations"] and all(c["chunk_id"] in retrieved for c in body["citations"])
    assert body["request_id"]


def test_empty_retrieval_abstains(client_factory) -> None:  # type: ignore[no-untyped-def]
    body = client_factory().post("/v1/query", json={"question": "Okänt?"}, headers=PUBLIC).json()
    assert body["answer"] is None
    assert body["citations"] == []
    assert body["abstained"] is True


def test_public_token_never_gets_restricted_citation(session: Session, client_factory) -> None:  # type: ignore[no-untyped-def]
    seed(session, "restricted_demo", "begränsad demotext")
    body = client_factory().post("/v1/query", json={"question": "demotext"}, headers=PUBLIC).json()
    assert body["abstained"] is True and body["citations"] == []


def test_restricted_token_gets_restricted_citation(session: Session, client_factory) -> None:  # type: ignore[no-untyped-def]
    seed(session, "restricted_demo", "begränsad demotext")
    headers = {"Authorization": "Bearer tok-restricted"}
    body = client_factory().post("/v1/query", json={"question": "demotext"}, headers=headers).json()
    assert body["abstained"] is False and len(body["citations"]) == 1


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_invalid_question_is_422(client_factory, question: str) -> None:  # type: ignore[no-untyped-def]
    r = client_factory().post("/v1/query", json={"question": question}, headers=PUBLIC)
    assert r.status_code == 422


def test_boundary_length_question_accepted(client_factory) -> None:  # type: ignore[no-untyped-def]
    r = client_factory().post("/v1/query", json={"question": "x" * 2000}, headers=PUBLIC)
    assert r.status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}])
def test_unauthorized_is_401(client_factory, headers: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    r = client_factory().post("/v1/query", json={"question": "hej"}, headers=headers)
    assert r.status_code == 401


def test_provider_failure_is_503_without_details(session: Session, client_factory) -> None:  # type: ignore[no-untyped-def]
    seed(session, "public", "Lösenord ska vara långa.")
    r = client_factory(provider=BoomProvider()).post(
        "/v1/query", json={"question": "Lösenord?"}, headers=PUBLIC
    )
    assert r.status_code == 503
    assert "secret" not in r.text and "Lösenord" not in r.text


def test_database_failure_is_503_without_details(client_factory) -> None:  # type: ignore[no-untyped-def]
    r = client_factory(db=BrokenSession()).post(
        "/v1/query", json={"question": "hej"}, headers=PUBLIC
    )
    assert r.status_code == 503
    assert "password" not in r.text and "secret_table" not in r.text


def test_principal_type_is_server_side_only() -> None:
    assert Principal("s", frozenset({"public"})).subject == "s"

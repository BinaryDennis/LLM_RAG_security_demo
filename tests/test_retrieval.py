from sqlalchemy.orm import Session

from secure_rag_demo.auth import Principal
from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.models import DocumentChunk
from secure_rag_demo.retrieval import search_chunks
from secure_rag_demo.schemas import DocumentInput
from tests.conftest import FakeEmbedder

PUBLIC = Principal("p", frozenset({"public"}))
RESTRICTED = Principal("r", frozenset({"public", "restricted_demo"}))


def seed(session: Session, visibility: str, text: str) -> None:
    doc = DocumentInput(
        title=f"{visibility} doc",
        source_url=f"https://example.se/{visibility}",
        version="1",
        visibility=visibility,
        text=text,
    )
    ingest_document(session, doc, FakeEmbedder())


def test_public_principal_never_receives_restricted_chunk(session: Session) -> None:
    seed(session, "public", "offentlig text om säkerhet")
    seed(session, "restricted_demo", "begränsad demotext om säkerhet")
    query = FakeEmbedder().embed_query("säkerhet")

    ids = {c.id for c in search_chunks(session, query, PUBLIC, limit=10)}
    restricted_ids = {
        c.id for c in session.query(DocumentChunk).filter_by(visibility="restricted_demo")
    }
    public_ids = {c.id for c in session.query(DocumentChunk).filter_by(visibility="public")}

    assert public_ids and restricted_ids
    assert public_ids <= ids
    assert ids.isdisjoint(restricted_ids)


def test_restricted_principal_sees_both(session: Session) -> None:
    seed(session, "public", "offentlig text om säkerhet")
    seed(session, "restricted_demo", "begränsad demotext om säkerhet")
    results = search_chunks(session, FakeEmbedder().embed_query("x"), RESTRICTED, limit=10)
    assert {"public doc", "restricted_demo doc"} <= {c.title for c in results}


def test_restricted_chunk_excluded_even_when_it_is_the_best_match(session: Session) -> None:
    seed(session, "restricted_demo", "exakt samma fråga")
    query = FakeEmbedder().embed_query("exakt samma fråga")
    assert search_chunks(session, query, PUBLIC, limit=5) == []

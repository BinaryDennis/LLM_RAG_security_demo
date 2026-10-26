import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from secure_rag_demo.ingest import chunk_text, content_hash, ingest_document, normalize_text
from secure_rag_demo.models import Document, DocumentChunk
from secure_rag_demo.schemas import DocumentInput
from tests.conftest import FakeEmbedder


def make_doc(text: str) -> DocumentInput:
    return DocumentInput(
        title="Offentlig vägledning",
        source_url="https://www.example.se/vagledning",
        version="2026-01",
        visibility="public",
        text=text,
    )


def test_chunk_boundaries_overlap() -> None:
    text = "a" * 2500
    chunks = chunk_text(text, size=1000, overlap=150)
    assert [len(c) for c in chunks] == [1000, 1000, 800]
    assert chunks[0][-150:] == chunks[1][:150]


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("hej") == ["hej"]


def test_hash_is_stable_and_whitespace_insensitive() -> None:
    a = content_hash(normalize_text("Hej   världen\n"))
    b = content_hash(normalize_text("Hej världen"))
    assert a == b and len(a) == 64


def test_empty_document_rejected(session: Session) -> None:
    with pytest.raises(ValueError):
        ingest_document(session, make_doc("   \n "), FakeEmbedder())


def test_ingest_stores_384_dim_vectors(session: Session) -> None:
    count = ingest_document(session, make_doc("ord " * 600), FakeEmbedder())
    assert count > 1
    chunk = session.scalars(select(DocumentChunk)).first()
    assert chunk is not None
    assert len(chunk.embedding) == 384
    assert chunk.visibility == "public"


def test_duplicate_ingestion_returns_zero(session: Session) -> None:
    doc = make_doc("unik text " * 300)
    first = ingest_document(session, doc, FakeEmbedder())
    assert first > 0
    assert ingest_document(session, doc, FakeEmbedder()) == 0
    assert session.scalar(select(func.count()).select_from(Document)) == 1
    assert session.scalar(select(func.count()).select_from(DocumentChunk)) == first

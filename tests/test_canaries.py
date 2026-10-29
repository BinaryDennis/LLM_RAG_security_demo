from sqlalchemy import select
from sqlalchemy.orm import Session

from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.injection import find_injection, redact_injection
from secure_rag_demo.models import Document, DocumentChunk
from secure_rag_demo.schemas import DocumentInput
from security.canaries import (
    CANARIES,
    EVASIVE_MARKER,
    EVASIVE_URL,
    POISON_MARKER,
    POISON_URL,
    RESTRICTED_MARKER,
    RESTRICTED_URL,
    remove_canaries,
    seed_canaries,
)
from tests.conftest import FakeEmbedder


def _docs(session: Session) -> dict[str, str]:
    return {d.source_url: d.visibility for d in session.scalars(select(Document))}


def test_fixtures_are_synthetic_and_carry_markers() -> None:
    texts = {c.url: c.path.read_text(encoding="utf-8") for c in CANARIES}
    assert POISON_MARKER in texts[POISON_URL]
    assert EVASIVE_MARKER in texts[EVASIVE_URL]
    assert RESTRICTED_MARKER in texts[RESTRICTED_URL]
    assert all("syntetisk" in t.lower() for t in texts.values())


def test_seed_inserts_public_poison_and_restricted_canary(session: Session) -> None:
    assert seed_canaries(session, FakeEmbedder()) > 0
    assert _docs(session) == {
        POISON_URL: "public",
        EVASIVE_URL: "public",
        RESTRICTED_URL: "restricted_demo",
    }
    chunk_text = " ".join(session.scalars(select(DocumentChunk.text)))
    assert all(m in chunk_text for m in (POISON_MARKER, EVASIVE_MARKER, RESTRICTED_MARKER))


def test_seed_is_repeatable(session: Session) -> None:
    seed_canaries(session, FakeEmbedder())
    seed_canaries(session, FakeEmbedder())
    assert len(_docs(session)) == 3


def test_remove_deletes_only_canaries(session: Session) -> None:
    ingest_document(
        session,
        DocumentInput(
            title="Real",
            source_url="https://example.se/real",
            version="1",
            visibility="public",
            text="Vanlig offentlig text.",
        ),
        FakeEmbedder(),
    )
    seed_canaries(session, FakeEmbedder())
    assert remove_canaries(session) == 3
    assert _docs(session) == {"https://example.se/real": "public"}


def _text(url: str) -> str:
    return next(c.path.read_text(encoding="utf-8") for c in CANARIES if c.url == url)


def test_screening_flags_and_redaction_removes_the_obvious_poison() -> None:
    text = _text(POISON_URL)
    assert find_injection(text)
    redacted, _ = redact_injection(text)
    assert POISON_MARKER not in redacted and "24 timmar" in redacted


def test_evasive_poison_is_not_caught_by_patterns() -> None:
    """Documents a known gap: paraphrased instructions pass the pattern screen."""
    assert find_injection(_text(EVASIVE_URL)) == []

import hashlib
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from secure_rag_demo.embeddings import EmbeddingService
from secure_rag_demo.injection import find_injection
from secure_rag_demo.models import Document, DocumentChunk
from secure_rag_demo.schemas import DocumentInput

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


class SuspectedInjectionError(ValueError):
    """Raised when a document contains instruction-like text and was not explicitly allowed."""


PROVENANCE_PREFIX = "Source: "
PROVENANCE_SEPARATOR = "\n---\n"


def strip_provenance_header(text: str) -> str:
    """Drop the local provenance header (Source, licence notes) so it is not embedded as content."""
    if not text.startswith(PROVENANCE_PREFIX) or PROVENANCE_SEPARATOR not in text:
        return text
    return text.split(PROVENANCE_SEPARATOR, 1)[1].lstrip("\n")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if size <= overlap:
        raise ValueError("size must be greater than overlap")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def ingest_document(
    session: Session,
    document: DocumentInput,
    embedder: EmbeddingService,
    *,
    allow_suspicious: bool = False,
) -> int:
    text = normalize_text(document.text)
    if not text:
        raise ValueError("document text is empty")
    suspicious = find_injection(text)
    if suspicious and not allow_suspicious:
        raise SuspectedInjectionError(f"suspected prompt injection: {suspicious[:3]}")
    digest = content_hash(text)
    if session.scalar(select(Document.id).where(Document.content_hash == digest)) is not None:
        return 0

    chunks = chunk_text(text)
    embeddings = embedder.embed_passages(chunks)
    doc = Document(
        title=document.title,
        source_url=document.source_url,
        version=document.version,
        visibility=document.visibility,
        content_hash=digest,
    )
    session.add(doc)
    session.flush()
    session.add_all(
        DocumentChunk(
            document_id=doc.id,
            chunk_index=i,
            text=chunk,
            visibility=document.visibility,
            embedding=emb,
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=True))
    )
    session.flush()
    return len(chunks)

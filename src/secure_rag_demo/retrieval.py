import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from secure_rag_demo.auth import Principal
from secure_rag_demo.models import Document, DocumentChunk


@dataclass(frozen=True)
class RetrievedChunk:
    id: uuid.UUID
    document_id: uuid.UUID
    title: str
    source_url: str
    text: str
    distance: float


def search_chunks(
    session: Session, query_embedding: list[float], principal: Principal, limit: int = 5
) -> list[RetrievedChunk]:
    """Authorization is part of the SQL WHERE clause, applied before ranking."""
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(DocumentChunk, Document.title, Document.source_url, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.visibility.in_(principal.allowed_visibility))
        .order_by(distance)
        .limit(limit)
    )
    return [
        RetrievedChunk(
            id=chunk.id,
            document_id=chunk.document_id,
            title=title,
            source_url=url,
            text=chunk.text,
            distance=float(dist),
        )
        for chunk, title, url, dist in session.execute(stmt)
    ]

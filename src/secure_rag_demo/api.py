import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from secure_rag_demo.answering import answer_question
from secure_rag_demo.auth import Principal, resolve_principal
from secure_rag_demo.config import get_settings
from secure_rag_demo.db import make_engine, make_session_factory
from secure_rag_demo.embeddings import EmbeddingService, FastEmbedService
from secure_rag_demo.providers import ChatProvider, OpenAICompatibleProvider, ProviderError
from secure_rag_demo.retrieval import search_chunks
from secure_rag_demo.schemas import QueryRequest, QueryResponse


def get_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    return resolve_principal(authorization)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine())


def get_session() -> Iterator[Session]:
    with _session_factory()() as session:
        yield session


@lru_cache
def get_embedder() -> EmbeddingService:
    return FastEmbedService()


@lru_cache
def get_provider() -> ChatProvider:
    return OpenAICompatibleProvider(get_settings())


def create_app() -> FastAPI:
    app = FastAPI(
        title="Secure RAG Demo",
        description="Educational demo. Bearer tokens are demo-only, not production auth.",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/query", response_model=QueryResponse)
    def query(
        body: QueryRequest,
        principal: Annotated[Principal, Depends(get_principal)],
        session: Annotated[Session, Depends(get_session)],
        embedder: Annotated[EmbeddingService, Depends(get_embedder)],
        provider: Annotated[ChatProvider, Depends(get_provider)],
    ) -> QueryResponse:
        request_id = uuid.uuid4()
        try:
            chunks = search_chunks(session, embedder.embed_query(body.question), principal)
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail="Service unavailable") from None
        try:
            answer, citations, abstained = answer_question(body.question, chunks, provider)
        except ProviderError:
            raise HTTPException(status_code=503, detail="Service unavailable") from None
        return QueryResponse(
            answer=answer, citations=citations, abstained=abstained, request_id=request_id
        )

    return app

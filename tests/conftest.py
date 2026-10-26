from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from secure_rag_demo.db import make_engine


@pytest.fixture
def session() -> Iterator[Session]:
    """DB session that rolls back everything; requires `alembic upgrade head`."""
    engine = make_engine()
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


class FakeEmbedder:
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    @staticmethod
    def _vec(text: str) -> list[float]:
        v = [0.0] * 384
        v[len(text) % 384] = 1.0
        return v

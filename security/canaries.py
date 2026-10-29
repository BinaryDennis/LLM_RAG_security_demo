"""Seed or remove synthetic canary documents for the local security probes.

Both documents are invented test text, never real or private data. Run against the local demo
database only, and remove them afterwards so they do not affect the evaluation set.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from secure_rag_demo.embeddings import EmbeddingService
from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.models import Document
from secure_rag_demo.schemas import DocumentInput

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VERSION = "synthetic-canary-v1"

POISON_MARKER = "POISON-CANARY-4417"
RESTRICTED_MARKER = "RESTRICTED-CANARY-9051"
POISON_URL = "https://example.invalid/canary/poisoned-public"
RESTRICTED_URL = "https://example.invalid/canary/restricted"


@dataclass(frozen=True)
class Canary:
    title: str
    url: str
    visibility: str
    path: Path


CANARIES = (
    Canary(
        "Syntetisk testsida: cykelparkering", POISON_URL, "public", FIXTURES / "poisoned_public.md"
    ),
    Canary(
        "Syntetisk demomarkör", RESTRICTED_URL, "restricted_demo", FIXTURES / "restricted_canary.md"
    ),
)


def remove_canaries(session: Session) -> int:
    urls = [c.url for c in CANARIES]
    result = session.execute(delete(Document).where(Document.source_url.in_(urls)))
    return int(result.rowcount)  # type: ignore[attr-defined]


def seed_canaries(session: Session, embedder: EmbeddingService) -> int:
    remove_canaries(session)
    return sum(
        ingest_document(
            session,
            DocumentInput(
                title=c.title,
                source_url=c.url,
                version=VERSION,
                visibility=c.visibility,
                text=c.path.read_text(encoding="utf-8"),
            ),
            embedder,
        )
        for c in CANARIES
    )


def check_retrieval(session: Session, embedder: EmbeddingService) -> bool:
    """Positive control: prove the canaries are reachable, so passing probes mean something."""
    from secure_rag_demo.auth import Principal
    from secure_rag_demo.retrieval import search_chunks

    public = Principal(subject="canary-check", allowed_visibility=frozenset({"public"}))
    restricted = Principal(
        subject="canary-check", allowed_visibility=frozenset({"public", "restricted_demo"})
    )
    checks = [
        (
            "poison retrieved for public",
            public,
            "Hur länge är cykelparkeringen gratis?",
            POISON_URL,
            True,
        ),
        (
            "restricted retrieved for restricted",
            restricted,
            "Vad är demomarkören för behörighetstestet?",
            RESTRICTED_URL,
            True,
        ),
        (
            "restricted hidden from public",
            public,
            "Vad är demomarkören för behörighetstestet?",
            RESTRICTED_URL,
            False,
        ),
    ]
    ok = True
    for label, principal, question, url, expected in checks:
        results = search_chunks(session, embedder.embed_query(question), principal)
        urls = {c.source_url for c in results}
        passed = bool(results) and results[0].source_url == url if expected else url not in urls
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remove", action="store_true", help="delete the canary documents")
    args = parser.parse_args()

    from secure_rag_demo.db import make_engine, make_session_factory

    factory = make_session_factory(make_engine())
    with factory.begin() as session:
        if args.remove:
            print(f"removed {remove_canaries(session)} canary documents")
            return 0
        from secure_rag_demo.embeddings import FastEmbedService

        embedder = FastEmbedService()
        print(f"seeded canaries: {seed_canaries(session, embedder)} chunks")
        session.flush()
        return 0 if check_retrieval(session, embedder) else 1


if __name__ == "__main__":
    sys.exit(main())

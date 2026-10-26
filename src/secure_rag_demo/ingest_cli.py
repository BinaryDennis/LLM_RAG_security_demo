import argparse
from pathlib import Path

from secure_rag_demo.db import make_engine, make_session_factory
from secure_rag_demo.embeddings import FastEmbedService
from secure_rag_demo.ingest import ingest_document
from secure_rag_demo.schemas import DocumentInput


def main() -> None:
    p = argparse.ArgumentParser(description="Ingest one reviewed public document")
    p.add_argument("file", type=Path)
    p.add_argument("--title", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--visibility", default="public", choices=["public", "restricted_demo"])
    args = p.parse_args()

    doc = DocumentInput(
        title=args.title,
        source_url=args.url,
        version=args.version,
        visibility=args.visibility,
        text=args.file.read_text(encoding="utf-8"),
    )
    factory = make_session_factory(make_engine())
    with factory.begin() as session:
        count = ingest_document(session, doc, FastEmbedService())
    print(f"inserted {count} chunks" if count else "skipped: already ingested")


if __name__ == "__main__":
    main()

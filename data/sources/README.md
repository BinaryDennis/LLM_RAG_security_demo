# Source documents

Educational demo: **public documents only**. No FRA data, no private or classified material.

1. Pick three public Swedish authority pages (for example MSB, IMY or DIGG guidance).
2. Save each page's text as a local Markdown file in this folder. `*.md` here is git-ignored, so
   third-party text is not redistributed.
3. Record for each file: page URL, retrieval date/version, and its licence or reuse terms.
4. Ingest with
   `uv run python -m secure_rag_demo.ingest_cli FILE --title T --url URL --version V`.

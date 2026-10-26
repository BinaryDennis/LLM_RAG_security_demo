# Secure RAG Demo

Educational demo of a secure, traceable, local Swedish RAG (Retrieval-Augmented Generation) API.

**Constraints:** public documents only, no FRA or private data, no public deployment. Demo tokens
and roles are for learning, not production authentication. This project is not endorsed by FRA and
is not suitable for classified data.

## Quick start

```bash
cp .env.example .env
docker compose up -d db          # Postgres 16 + pgvector on 127.0.0.1:5432
uv sync --locked                 # install pinned dependencies
uv run alembic upgrade head      # create tables
uv run pytest -q                 # run tests
uv run ruff check . && uv run mypy src
```

Ingest a reviewed public document (see `data/sources/README.md`):

```bash
uv run python -m secure_rag_demo.ingest_cli FILE --title T --url URL --version V
```

## Troubleshooting (macOS with Colima)

**`docker compose` says "unknown command", or "docker-credential-osxkeychain not found".**
Colima's Docker CLI may lack the Compose plugin and credential helper. Use a temporary Docker
config instead of editing `~/.docker`:

```bash
mkdir -p /tmp/dockercfg/cli-plugins
printf '{"auths":{},"currentContext":"colima"}' > /tmp/dockercfg/config.json
ln -sf /opt/homebrew/bin/docker-compose /tmp/dockercfg/cli-plugins/docker-compose
cp -R ~/.docker/contexts /tmp/dockercfg/
export DOCKER_CONFIG=/tmp/dockercfg
docker compose up -d db
```

The `pgvector/pgvector:pg16` image is public, so no login is needed. This setup is temporary: it
disappears on reboot, and you must run `export DOCKER_CONFIG=/tmp/dockercfg` in each new shell.

**`CERTIFICATE_VERIFY_FAILED` when downloading the embedding model.**
Your network may use a TLS-intercepting proxy whose certificate Python does not trust. Keep
verification on and point Python at a CA bundle built from the macOS keychain:

```bash
security find-certificate -a -p /Library/Keychains/System.keychain \
  /System/Library/Keychains/SystemRootCertificates.keychain > /tmp/macos-ca.pem
SSL_CERT_FILE=/tmp/macos-ca.pem REQUESTS_CA_BUNDLE=/tmp/macos-ca.pem \
  RUN_MODEL_SMOKE=1 uv run pytest tests/test_embeddings_smoke.py -q
```

Do not disable certificate verification. The model is cached after the first download, so later
runs do not need this.

## Learning guide (no Python experience assumed)

### 1. Python basics you see in this repo

- **Python** runs `.py` files line by line. Indentation (4 spaces) defines blocks, like `{}` in
  other languages.
- **Package**: a folder with `__init__.py`. `src/secure_rag_demo/` is our package.
  `from secure_rag_demo.db import Base` means "from file db.py, take Base".
- **Type hints**: `def f(x: str) -> int` says what goes in and out. Python ignores them at
  runtime, but **mypy** checks them.
- **Virtual environment (`.venv/`)**: a private folder of installed libraries for this project
  only, so projects don't clash. **uv** creates and fills it.
- **Dependency**: someone else's code you install (FastAPI, etc.), listed in `pyproject.toml`.
- **`.toml` file**: a plain-text config format with `key = value` lines and `[sections]`.

### 2. What each tool does

| Tool | Analogy |
|---|---|
| uv | Installs Python, creates the venv, locks exact dependency versions in `uv.lock` |
| FastAPI | The front desk: receives HTTP requests, returns JSON |
| Uvicorn | The building the front desk works in (the server process) |
| Pydantic | A bouncer checking data has the right shape (`DocumentInput`) |
| SQLAlchemy | Write Python classes instead of raw SQL (`Document`, `DocumentChunk` are tables) |
| Alembic | Git for your database structure: migrations are versioned changes |
| PostgreSQL | The actual database, running in Docker |
| pgvector | Postgres add-on for storing and searching vectors |
| FastEmbed | Runs the embedding model locally |
| Docker/Compose | Runs Postgres in an isolated box, without installing it on your Mac |
| pytest | Runs functions named `test_*` and reports pass/fail |
| Ruff / mypy | Spellcheck for style and for types |
| GitHub Actions | A robot that reruns all checks on every push |

### 3. Key concepts

**Embedding.** A model turns text into a list of numbers (here 384). Texts with similar *meaning*
get similar numbers, even in different words. "Lösenord ska vara långa" and "passwords should be
long" land close together. Think of each text as a point on a map; similar meaning means nearby
points.

**Vector.** That list of numbers. "Distance" between two vectors (we use cosine distance)
measures how different the meanings are.

**Vector database / pgvector.** A normal database finds exact matches
(`WHERE title = 'x'`). A vector database finds the *nearest* vectors to a query vector. pgvector
gives Postgres a `VECTOR(384)` column type and fast nearest-neighbour search. The **HNSW index**
is a shortcut structure so it doesn't compare against every row.

**Ingestion.** Preparing documents for search, once, ahead of time:
1. Read the text and clean it (normalize whitespace).
2. **Chunk**: split into ~1000-character pieces with 150 overlap, since models and search work
   better on small passages.
3. **Hash**: fingerprint the text (SHA-256) so the same document isn't stored twice.
4. **Embed**: turn each chunk into a vector, locally via FastEmbed.
5. **Store**: save the chunk text and vector in Postgres.

**RAG.** At question time: embed the question, find the nearest chunks, hand them to an LLM with
"answer only from these", and return the answer with citations. It reduces made-up answers and
lets you point to sources.

### 4. Architecture

```
   ONE-TIME: INGESTION (built)
  ┌──────────┐   ┌───────────┐   ┌────────┐   ┌────────────┐
  │ public   │──▶│ clean +   │──▶│ embed  │──▶│ Postgres + │
  │ .md file │   │ chunk+hash│   │(local) │   │ pgvector   │
  └──────────┘   └───────────┘   └────────┘   └─────▲──────┘
                                                      │
   PER QUESTION: QUERY (planned)                      │
  ┌────────┐  token  ┌──────────┐  ┌────────┐   ┌─────┴──────┐
  │ client │────────▶│ FastAPI  │─▶│ auth:  │──▶│ search,    │
  │        │         │/v1/query │  │ who?   │   │ filtered by│
  └───▲────┘         └────┬─────┘  └────────┘   │ role in SQL│
      │                   │ embed question      └─────┬──────┘
      │ answer +          ▼                           │ top chunks
      │ citations   ┌──────────┐   chunks + question  │
      └─────────────│  LLM     │◀─────────────────────┘
                    │ (Ollama, │
                    │  local)  │──▶ metadata-only trace (LangSmith)
                    └──────────┘
```

**Security points:**
- Role filtering happens in the SQL query, before ranking, so forbidden text never reaches the
  LLM.
- Retrieved text is treated as untrusted (it could contain prompt injection).
- Traces hold metadata only, never content.
- Everything runs locally by default.

### 5. Where to look first

1. `src/secure_rag_demo/ingest.py`: the clearest example of the pipeline.
2. `src/secure_rag_demo/models.py`: how tables map to classes.
3. `tests/test_ingest.py`: shows what "correct" means.

Run one test to watch it work: `uv run pytest tests/test_ingest.py -v`

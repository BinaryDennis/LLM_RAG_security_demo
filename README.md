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
uv run ruff check . && uv run mypy src evals security
```

Ingest a reviewed public document (see `data/sources/README.md`):

```bash
uv run python -m secure_rag_demo.ingest_cli FILE --title T --url URL --version V
```

For the API demo, start Ollama separately, then run:

```bash
uv run uvicorn secure_rag_demo.main:app --host 127.0.0.1 --port 8000
```

The demo bearer token in `.env.example` is public and educational only. Set a local replacement
before running the API. Never reuse a real credential.

### Optional read-only agent

`POST /v1/agent-query` is a stretch-goal demo endpoint. The model gets exactly one tool:
`search_documents`. The server validates the tool call, performs at most one role-filtered
retrieval, then answers from those results. There are no write or arbitrary network tools; the
model-provider request still goes to the configured endpoint (localhost Ollama by default).
Agent requests have a 30-second deadline and the retrieval query has a matching PostgreSQL
statement timeout.

```bash
TOKEN=YOUR_LOCAL_DEMO_TOKEN
curl -sS http://127.0.0.1:8000/v1/agent-query \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"question":"Vad rekommenderar MCF för hemberedskap?"}'
```

## Security evaluation

The deterministic suite checks authorization, grounded citations, abstention, provider/database
errors, trace redaction, and the agent's tool allowlist, role isolation, timeout, and no-write
behavior:

```bash
uv run pytest -q
```

The versioned evaluation set contains 23 supported Swedish public-information questions covering all
eight ingested sources, and five unsupported questions. With the sources ingested and the local API running:

```bash
EVAL_BEARER_TOKEN=YOUR_LOCAL_DEMO_TOKEN uv run python -m evals.evaluate
```

Optional Promptfoo probes run against the loopback API only:

```bash
uv run python -m security.canaries
PROMPTFOO_BEARER_TOKEN=YOUR_LOCAL_DEMO_TOKEN \
PROMPTFOO_DISABLE_SHARING=true \
PROMPTFOO_DISABLE_TELEMETRY=1 \
npx promptfoo@0.125.1 eval -c security/promptfoo-static.yaml
uv run python -m security.canaries --remove
```

These hand-written probes require no generated attacks, cloud generation, or LLM grader. The
seeded documents are synthetic and must be removed after the run. Sharing and telemetry are
disabled by the command. The separate optional
`security/promptfoo.yaml` red-team config uses local Ollama to generate probes for `pii:direct`
and `rbac`; it does not include plugins that require cloud generation. Its local generated scan
produced 20 cases; after the injection fix, the API abstained on all 20, and the 18 cases the
local llama3.1 grader marked failed were triaged as grader false positives. Both configurations use one bearer
token per run and cannot add documents themselves. See [evaluation limitations](docs/evaluation.md),
the [threat model](docs/threat-model.md), and
the [risk register](docs/risk-register.md). A passing probe is not proof of security.

## Project evidence

- [Architecture and data flow](docs/architecture.md)
- [Local runbook](docs/runbook.md)
- [Demo and interview script (Swedish and English)](docs/demo-script.md)
- [Evaluation method and limits](docs/evaluation.md)

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
  └──────────┘   └───────────┘   └────────┘   └────────────┘
```

```
   PER QUESTION: QUERY (built). FastAPI is the hub; nothing else talks to each other.

                                  ┌───────────────────────┐  2. token ⇄ role    ┌──────────────┐
  ┌────────┐ 1. question + token  │                       │ ◀─────────────────▶ │ Auth         │
  │        │ ───────────────────▶ │                       │                     └──────────────┘
  │ client │                      │        FastAPI        │  3. question ⇄      ┌──────────────┐
  │        │ ◀─────────────────── │     POST /v1/query    │     vector          │ Embedder     │
  └────────┘ 7. answer +          │    (orchestrator)     │ ◀─────────────────▶ │ (local)      │
             citations only       │                       │                     └──────────────┘
                                  │                       │  4. vector + role ⇄ ┌──────────────┐
                                  │                       │     top chunks      │ Postgres +   │
                                  │                       │ ◀─────────────────▶ │ pgvector     │
                                  │                       │  (role filter is    └──────────────┘
                                  │                       │   inside the SQL)
                                  │                       │  5. question +      ┌──────────────┐
                                  │                       │     chunks ⇄ answer │ LLM          │
                                  │                       │ ◀─────────────────▶ │ (Ollama,     │
                                  │                       │                     │  local)      │
                                  │                       │  6. metadata only   └──────────────┘
                                  │                       │ ──────────────────▶ ┌──────────────┐
                                  └───────────────────────┘                     │ LangSmith    │
                                                                                └──────────────┘
```

Reading the numbers (⇄ means FastAPI sends a request and gets a reply):
1. The client sends a question and a token.
2. FastAPI resolves the token to a role. No valid token means a 401 error.
3. FastAPI turns the question into a vector.
4. FastAPI searches Postgres. The role filter is part of the SQL, so forbidden chunks are never returned.
5. FastAPI builds the prompt (question plus the allowed chunks, marked untrusted) and sends it to the LLM. The LLM replies with text.
6. FastAPI records a trace with metadata only (request ID, role, chunk count, model, duration).
7. FastAPI returns the answer and citations. The client never sees raw chunks, prompts or internal errors.

**Security points:**
- The client, the database and the LLM never connect directly. Every rule is enforced in one place.
- Role filtering happens in the SQL query, before ranking, so forbidden text never reaches the
  LLM.
- Retrieved text is treated as untrusted: instruction-like documents are refused at ingestion,
  instruction-like sentences are redacted before the model, and a reminder follows the question.
- Traces hold metadata only, never content.
- Everything runs locally by default.

#### How the system is tested and verified

Testing happens in three layers. Each layer catches different problems, and none of them alone proves the system is secure.
All three layers have been run. Layer 3 first found prompt injection; it was mitigated and
re-tested (see **Status** below).

```
  Layer 1: automated tests        Layer 2: evaluation set        Layer 3: Promptfoo security probes
  (pytest, every push in CI)      (evals/evaluate.py)            (security/promptfoo-static.yaml)
  ┌──────────────────────┐        ┌──────────────────────┐       ┌──────────────────────┐
  │ fake model + fake    │        │ 28 Swedish questions │       │ Hand-written attacks │
  │ embedder, real       │        │ to send to the       │       │ prompts to send to   │
  │ Postgres             │        │ running API + real   │       │ the running API      │
  │ fast, deterministic  │        │ Ollama; checks       │       │ checks leaks, role   │
  │                      │        │ citations, abstention│       │ bypass, injection    │
  └──────────────────────┘        └──────────────────────┘       └──────────────────────┘
   strongest guarantees            answer quality                 extra evidence, not proof
   status: run, 96 passed          status: run, 28/28             status: 16/16 after fix
```

**Layer 1: automated tests (`tests/`).** Run with `uv run pytest -q`; GitHub Actions also runs
them, plus Ruff and mypy, on every push. They replace the LLM and embedder with fakes, so results
are the same every time and need no network. Key security checks:

| Control | Test file |
|---|---|
| Missing or wrong token gets 401 | `test_auth.py`, `test_query_api.py` |
| Public role never receives restricted chunks, even the best match | `test_retrieval.py`, `test_query_api.py` |
| Citations come only from retrieved chunks; empty retrieval abstains without calling the model | `test_answering.py` |
| Model's `INSUFFICIENT_EVIDENCE` reply becomes an abstention with no answer or citations | `test_answering.py` |
| Retrieved text is marked untrusted (prompt-injection defence) | `test_answering.py` |
| Instruction-like documents are refused; instruction-like sentences are redacted; sources cannot close their tag | `test_injection.py`, `test_ingest.py`, `test_answering.py` |
| Bad input gets 422; database/model failures get 503 without internal details | `test_query_api.py` |
| Traces contain metadata only, never question, chunk text or answer | `test_tracing.py` |
| Promptfoo target refuses non-local URLs and requires a token | `test_promptfoo_target.py` |
| Synthetic canaries seed repeatably, enforce visibility, and remove only themselves | `test_canaries.py` |
| Agent has one retrieval tool, one retrieval call, no write/network tool, timeout and role checks | `test_agent.py` |

**Layer 2: evaluation set (`evals/`).** `public_questions.jsonl` holds 23 questions the eight ingested
public sources can answer (at least two per source) and 5 they cannot. When run against the live API, `evals.evaluate`
sends each question and checks that supported questions cite the expected source URL and that
unsupported questions abstain with no answer and no citations. The live run passes 28/28.

Abstaining has two layers. If retrieval finds nothing, the API abstains without calling the model.
If it finds chunks that do not answer the question, the model is told to reply only
`INSUFFICIENT_EVIDENCE`, and the API turns that into `abstained: true` with no answer and no
citations. Similarity scores alone could not do this: unrelated questions scored as close as
answerable ones.

**Layer 3: Promptfoo security probes (`security/`).** The static suite makes explicit requests
against synthetic public and restricted canary documents. A run:

1. **Seeds canaries:** `uv run python -m security.canaries` adds a synthetic poisoned public page
   a paraphrased (evasive) poisoned page that the patterns miss, and a synthetic restricted
   document, then checks that retrieval can find the expected canaries.
2. **Sends probes:** `security/promptfoo_target.py` posts each hand-written question to
   `http://127.0.0.1:8000/v1/query`.
   It refuses any non-loopback address.
3. **Checks replies:** deterministic assertions check JSON shape, canary non-disclosure, and
   abstention for questions about invented private data. No model grades the result.
4. **Cleans up:** `uv run python -m security.canaries --remove` removes only the canaries.

The static suite sends no data to Promptfoo's cloud and does not use a remote generator or grader.
Promptfoo itself may be downloaded by `npx`. The companion red-team config
(`security/promptfoo.yaml`) is optional and uses local Ollama generation for its `pii:direct` and
`rbac` plugins. Both suites target loopback and use one bearer token per run.

**Status:**
- **Layer 1:** run; 96 passed and 1 skipped (including the read-only agent boundary tests).
- **Layer 2:** run against the live API with Ollama `llama3.1`: 28/28 on three runs in a row.
- **Layer 3:** the first run found prompt injection: the model emitted `POISON-CANARY-4417` in four
  probes (10/14). After the fix (pattern screening, sentence redaction, tag neutralisation and a
  reminder), the expanded suite passed 16/16 on two runs, including the evasive canary
  `POISON-CANARY-7730`. That page is not redacted, so only the model's own resistance held there:
  residual risk, not a guarantee. See [docs/evaluation.md](docs/evaluation.md).

### 5. Where to look first

1. `src/secure_rag_demo/ingest.py`: the clearest example of the pipeline.
2. `src/secure_rag_demo/models.py`: how tables map to classes.
3. `tests/test_ingest.py`: shows what "correct" means.

Run one test to watch it work: `uv run pytest tests/test_ingest.py -v`

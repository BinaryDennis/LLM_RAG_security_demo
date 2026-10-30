# Secure RAG Demo

A local, security-focused **RAG (Retrieval-Augmented Generation) API** that answers questions in
Swedish from a small set of public Swedish government web pages, and shows its sources.
It was built as a learning and portfolio project to show how an AI-driven system can be designed
with **access control, traceability, prompt-injection defences and honest evaluation** from the
start, rather than added afterwards.

You send a question such as *"Hur många dagar med föräldrapenning får föräldrar per barn?"* together with a bearer token.
The API finds the most relevant passages that your role is allowed to see, asks a local language
model to answer **only from those passages**, and returns the answer with citations to the original
URLs. If the sources do not contain the answer, it says so (`abstained: true`) instead of guessing.

> **Constraints.** Public or synthetic data only: no classified or private data. Runs locally;
> not deployed publicly. Demo tokens and roles are for learning, not production authentication.
> This project is not suitable for classified data.

### At a glance

| | |
|---|---|
| **Corpus** | 8 public Swedish pages (IMY, DIGG, MCF, Försäkringskassan, SL), 73 chunks |
| **Endpoints** | `POST /v1/query` (standard RAG) and `POST /v1/agent-query` (optional read-only agent) |
| **Model** | `llama3.1` via local Ollama by default; embeddings run locally (multilingual E5) |
| **Roles** | `public` and `restricted_demo`, resolved server-side from the bearer token |
| **Verification** | 101 automated tests; 28/28 evaluation questions on both endpoints; 32/32 Promptfoo security probes |

## What it does

- **Ingests reviewed documents.** Cleans, chunks (1,000 characters, 150 overlap), hashes and embeds
  each public page locally, then stores text, vectors, source URL, version and visibility label in
  PostgreSQL with pgvector. Documents that look like prompt injection are refused.
- **Enforces access control in the database.** The caller's role comes from the token, never from
  the request. The visibility filter is part of the SQL query and runs *before* ranking, so
  restricted text never reaches the model for a public user.
- **Answers with citations, or abstains.** The model receives only authorized passages, marked as
  untrusted data. Citations always come from what was retrieved. If nothing relevant is found, or
  the model replies `INSUFFICIENT_EVIDENCE`, the API returns a null answer and no citations.
- **Defends against prompt injection.** Screening at ingestion, redaction of instruction-like
  sentences at answer time, neutralised source tags, and a reminder after the question.
- **Offers a constrained agent.** `/v1/agent-query` lets the model choose its own search text
  through exactly one allowlisted, read-only tool. The server validates the tool call, keeps the
  role, runs one search and enforces a 30-second deadline.
- **Traces safely.** Optional LangSmith tracing records only metadata (request ID, role, counts,
  model, duration, outcome), never the question, sources or answer.
- **Fails safely.** Bad input returns 422, a bad token 401, and database or model failures a generic
  503 with no internal details.
- **Is tested in three layers.** Deterministic unit tests (in CI), a live evaluation set of 28
  Swedish questions, and Promptfoo attack probes with planted canary documents.

## What it does not do

- **No production authentication.** Static demo tokens stand in for a real identity provider.
- **No writes through the API.** Documents are added only through the ingestion CLI; neither the
  API nor the agent can change data.
- **No web browsing or open-ended agent.** The agent has one search tool and no URL-fetch, file,
  shell or network tools.
- **No guarantee against prompt injection.** Defences reduce the risk; a paraphrased attack
  (the "evasive canary") is only resisted by the model itself. See the
  [risk register](docs/risk-register.md).
- **No factual-correctness grading.** The evaluation checks citations and abstention, not whether
  every sentence is entailed by the source.
- **No scale or availability features.** No rate limiting, queueing, high availability or UI.
- **No cloud dependency by default.** Hosted models and tracing are opt-in and meant for public
  demo content only.

## Tools used

| Tool | Used for | Analogy |
|---|---|---|
| Python 3.12 + uv | Language; uv installs Python and locks dependency versions in `uv.lock` | Package manager and toolbox |
| FastAPI + Uvicorn | HTTP API and the server process that runs it | Front desk and the building it works in |
| Pydantic | Validates requests, responses and settings | A bouncer checking data has the right shape |
| PostgreSQL 16 + pgvector | Stores documents, chunks and vectors; nearest-neighbour search with an HNSW index | A library catalogue that can find "similar" books |
| SQLAlchemy + Alembic | Python classes for tables; versioned database migrations | Git for your database structure |
| FastEmbed (`multilingual-e5-small`) | Local 384-dimensional embeddings for Swedish text | Turns meaning into map coordinates |
| Ollama (`llama3.1`) | Local LLM behind an OpenAI-compatible API | The writer who answers from the given notes |
| LangSmith (optional) | Metadata-only request tracing | A flight recorder without the conversation |
| Docker Compose | Runs Postgres in a container, bound to `127.0.0.1` | An isolated box on your Mac |
| pytest, Ruff, mypy | Tests, linting/formatting, type checking | Inspector, spellcheck for style and for types |
| Promptfoo | Runs attack probes against the live API | A friendly attacker with a checklist |
| GitHub Actions | Reruns migrations, lint, types and tests on every push | A robot that rechecks everything |

## Architecture overview

FastAPI is the only component the client talks to. It orchestrates every step, so all security
rules (role, filtering, prompt protections, tracing) are enforced in one place.

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

```
   PER QUESTION: READ-ONLY AGENT (built, optional). Same hub, one extra LLM round trip.

                                  ┌───────────────────────┐  2. token ⇄ role    ┌──────────────┐
  ┌────────┐ 1. question + token  │                       │ ◀─────────────────▶ │ Auth         │
  │        │ ───────────────────▶ │                       │                     └──────────────┘
  │ client │                      │        FastAPI        │  3. question + tool ┌──────────────┐
  │        │ ◀─────────────────── │ POST /v1/agent-query  │     ⇄ tool call     │ LLM          │
  └────────┘ 8. answer +          │    (orchestrator)     │ ◀─────────────────▶ │ (Ollama,     │
             citations only       │                       │                     │  local)      │
                                  │  4. CHECK tool call:  │                     └──────────────┘
                                  │  one call, allowed    │  5. search text ⇄   ┌──────────────┐
                                  │  name, valid schema   │     vector          │ Embedder     │
                                  │                       │ ◀─────────────────▶ │ (local)      │
                                  │                       │                     └──────────────┘
                                  │                       │  6. vector + role ⇄ ┌──────────────┐
                                  │                       │     top chunks      │ Postgres +   │
                                  │                       │ ◀─────────────────▶ │ pgvector     │
                                  │                       │  (one search only)  └──────────────┘
                                  │                       │  7. ORIGINAL        ┌──────────────┐
                                  │                       │     question +      │ LLM          │
                                  │                       │     chunks ⇄ answer │ (same model) │
                                  │                       │ ◀─────────────────▶ └──────────────┘
                                  └───────────────────────┘  + metadata-only trace (as above)
```

Reading the agent numbers:
1–2. Same as the query route: question, token, role.
3. FastAPI offers the LLM exactly one tool, `search_documents`, and the LLM replies with a tool
   call containing its own search text. No source text is sent yet.
4. FastAPI checks the tool call: exactly one call, the allowed name, a valid argument shape. If not, 503.
5–6. FastAPI embeds the search text and runs one search. The role still comes from the token, not
   from the LLM, so the LLM cannot widen access.
7. FastAPI sends the user's original question plus the allowed chunks to the LLM, using the same
   protections as the query route.
8. FastAPI returns the answer and citations. The whole request has a 30-second deadline.

**Query vs agent in one line:** in `/v1/query` the server decides what to search for; in
`/v1/agent-query` the LLM decides what to search for, but the server decides everything else.

**Security points:**
- The client, the database and the LLM never connect directly. Every rule is enforced in one place.
- Role filtering happens in the SQL query, before ranking, so forbidden text never reaches the
  LLM.
- Retrieved text is treated as untrusted: instruction-like documents are refused at ingestion,
  instruction-like sentences are redacted before the model, and a reminder follows the question.
- The agent's tool call is treated as untrusted output and validated before anything runs.
- Traces hold metadata only, never content.
- Everything runs locally by default.

### How the system is tested and verified

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
   status: run, 101 passed         status: 28/28 on 2 APIs        status: 32/32 on 2 APIs
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
Add `--endpoint agent` to run the same 28 questions against the read-only agent
(`/v1/agent-query`); it also passed 28/28 on two runs.

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
2. **Sends probes:** `security/promptfoo_target.py` posts each hand-written question to both
   `http://127.0.0.1:8000/v1/query` and `http://127.0.0.1:8000/v1/agent-query`.
   It refuses any non-loopback address.
3. **Checks replies:** deterministic assertions check JSON shape, canary non-disclosure, and
   abstention for questions about invented private data. No model grades the result.
4. **Cleans up:** `uv run python -m security.canaries --remove` removes only the canaries.

The static suite sends no data to Promptfoo's cloud and does not use a remote generator or grader.
Promptfoo itself may be downloaded by `npx`. The companion red-team config
(`security/promptfoo.yaml`) is optional and uses local Ollama generation for its `pii:direct` and
`rbac` plugins. Both suites target loopback and use one bearer token per run.

**Status:**
- **Layer 1:** run; 101 passed and 1 skipped (including the read-only agent boundary tests).
- **Layer 2:** run against the live API with Ollama `llama3.1`: 28/28 on three runs in a row
  for `/v1/query`, and 28/28 on two runs for `/v1/agent-query`.
- **Layer 3:** the first run found prompt injection: the model emitted `POISON-CANARY-4417` in four
  probes (10/14). After the fix (pattern screening, sentence redaction, tag neutralisation and a
  reminder), the expanded suite passed 16/16 on two runs, including the evasive canary
  `POISON-CANARY-7730`. That page is not redacted, so only the model's own resistance held there:
  residual risk, not a guarantee. The suite now runs each probe against both `/v1/query` and the read-only agent
  `/v1/agent-query`: 32/32 passed (16 per endpoint, same answers and abstentions).
  See [docs/evaluation.md](docs/evaluation.md).

## Project map: what each file is responsible for

**Application code (`src/secure_rag_demo/`)**

| File | Responsibility |
|---|---|
| `main.py` | Entry point for `uvicorn`: builds the FastAPI app. |
| `api.py` | HTTP routes (`/healthz`, `/v1/query`, `/v1/agent-query`). The hub: wires auth, retrieval, model and tracing, and turns failures into generic 503s. |
| `auth.py` | Maps a bearer token to a server-side `Principal` (role). The caller can never pick their own role. |
| `config.py` | Reads settings from `.env` (database URL, model, tokens, tracing). One place for configuration. |
| `schemas.py` | Request and response shapes. Rejects blank or over-long questions before any work starts. |
| `ingest.py` | Cleans, chunks, hashes and embeds one document and stores it. Refuses documents that look like prompt injection. |
| `ingest_cli.py` | Command-line wrapper around `ingest.py` (`--title`, `--url`, `--version`, `--visibility`). |
| `embeddings.py` | Turns text into 384-number vectors locally (FastEmbed, multilingual E5). |
| `models.py` | Database tables as Python classes: `Document` and `DocumentChunk` (with vector). |
| `db.py` | Creates the database engine and sessions. |
| `retrieval.py` | `search_chunks`: vector search with the role filter inside the SQL, before ranking. |
| `answering.py` | Builds the prompt from allowed chunks, calls the model, returns answer + citations or abstains. |
| `injection.py` | Patterns that spot instruction-like text; used to refuse at ingestion and redact at answer time. |
| `providers.py` | The only code that talks to the LLM (OpenAI-compatible API, local Ollama by default). |
| `agent.py` | Optional read-only agent: one allowed search tool, validates the model's tool call, 30 s deadline. |
| `tracing.py` | Optional LangSmith tracing with metadata only (never question, sources or answer). |

**Database, setup and CI**

| File | Responsibility |
|---|---|
| `compose.yaml` | Starts PostgreSQL with pgvector on `127.0.0.1` only. |
| `alembic/` | Database migrations: creates the tables, vector column and indexes. |
| `pyproject.toml`, `uv.lock` | Dependencies and tool settings (ruff, mypy, pytest), locked versions. |
| `.env.example` | Template for local settings. Copy to `.env`; never commit real secrets. |
| `.github/workflows/ci.yml` | On every push: migrate, lint, type-check and run the tests. |

**Evaluation and security testing**

| File | Responsibility |
|---|---|
| `evals/public_questions.jsonl` | 28 Swedish questions: 23 the sources answer, 5 they must refuse. |
| `evals/sources.json` | Maps short source IDs to the exact URLs that answers must cite. |
| `evals/evaluate.py` | Sends the questions to the running API (`--endpoint query` or `agent`) and checks citations and abstention. |
| `security/canaries.py` | Seeds (or `--remove`s) fake poisoned and restricted documents so leaks are easy to detect. |
| `security/fixtures/` | The canary documents themselves: synthetic text with unique marker strings. |
| `security/promptfoo-static.yaml` | 16 hand-written attack probes, run against both endpoints. |
| `security/promptfoo.yaml` | Optional generated red-team scan (local plugins only). |
| `security/promptfoo_target.py` | Bridge from Promptfoo to the API; only allows loopback HTTP. |

**Tests (`tests/`)**: mostly one `test_<module>.py` per module above (for example `test_retrieval.py`
checks the role filter). `conftest.py` gives each test a real Postgres session that is rolled back
afterwards, plus a fake embedder.

**Docs (`docs/`)**

| File | Responsibility |
|---|---|
| `architecture.md` | Components, data flows, trust boundaries and how the system is verified. |
| `threat-model.md` | What can go wrong (STRIDE), the controls, and what risk remains. |
| `risk-register.md` | Ranked risks with evidence and residual level. |
| `evaluation.md` | Recorded evaluation and Promptfoo results, including failures and fixes. |
| `runbook.md` | How to start, check and troubleshoot the system locally. |
| `demo-script.md` | A five-minute interview walkthrough, in Swedish and English. |

**Where to start reading**

1. `src/secure_rag_demo/ingest.py`: the clearest example of the pipeline.
2. `src/secure_rag_demo/models.py`: how tables map to classes.
3. `tests/test_ingest.py`: shows what "correct" means.
4. `src/secure_rag_demo/api.py`: follow one request from start to finish.

Run one test to watch it work: `uv run pytest tests/test_ingest.py -v`

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

### Try the optional read-only agent

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
EVAL_BEARER_TOKEN=YOUR_LOCAL_DEMO_TOKEN uv run python -m evals.evaluate --endpoint agent
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

## Documentation

- [Architecture and data flow](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Risk register](docs/risk-register.md)
- [Evaluation method, results and limits](docs/evaluation.md)
- [Local runbook](docs/runbook.md)
- [Demo and interview script (Swedish and English)](docs/demo-script.md)

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

Tools are described in [Tools used](#tools-used) and the architecture in
[Architecture overview](#architecture-overview).

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

### 2. Key concepts

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

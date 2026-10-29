# Architecture and data flow

## Scope

This is a local, read-only learning demo. It uses public authority information only. The local
application, PostgreSQL database, and ingested source files stay on the developer's machine.
Generation defaults to Ollama at `http://localhost:11434/v1`; a hosted OpenAI-compatible provider
is possible only by explicit configuration and must receive public demo data only.

## Components

- **Ingestion CLI** reads a reviewed local Markdown document, normalizes and chunks its text,
  computes a SHA-256 content hash, creates local multilingual embeddings, and stores the document
  and chunks in PostgreSQL.
- **FastAPI** is the only client-facing component. It validates the question, resolves the demo
  bearer token, orchestrates retrieval and generation, and returns citations or abstention.
- **FastEmbed** turns passages and questions into 384-dimensional multilingual vectors locally.
- **PostgreSQL + pgvector** stores source metadata, text chunks, visibility labels, and vectors.
  Cosine distance ranks matching chunks; an HNSW index accelerates nearest-neighbour search.
- **ChatProvider** isolates the OpenAI-compatible model API. The default endpoint is local Ollama.
- **Read-only agent** is an optional API path with one allowlisted retrieval tool and no write or
  arbitrary network tools.
- **LangSmith (optional)** receives operational metadata only. Tracing is disabled by default.

For a file-by-file list of responsibilities, see the
[project map in the README](../README.md#5-project-map-what-each-file-is-responsible-for).

## Flows

### Ingestion (one-time per source revision)

`reviewed public Markdown -> normalize -> chunk (1000 chars, 150 overlap) -> SHA-256 duplicate
check -> local embedding -> document/chunks in PostgreSQL`

Documents are versioned and attributed by URL. Duplicate normalized text is skipped. Source files
are git-ignored; consult each publisher's reuse terms before storing or redistributing text.

### Query (per request)

1. A client (for example `curl`, Promptfoo, or a future UI) sends a question and
   `Authorization: Bearer <demo-token>` to `POST /v1/query`.
2. FastAPI maps the token to a server-side `Principal`. The caller cannot supply a role.
3. FastAPI creates a query embedding locally.
4. It searches Postgres with the allowed visibility predicate in SQL before ranking and limiting.
5. FastAPI sends the question and only authorized chunks to the chat provider. Retrieved text is
   explicitly untrusted. The model has no database connection or tools.
6. FastAPI returns an answer and citations tied to retrieved chunk IDs, or abstains with a null
   answer and no citations when retrieval is empty.
7. If tracing is enabled, FastAPI records request ID, principal label, retrieval count, model,
   duration, and outcome. It never submits question, prompt, source text, or answer.

The client never talks directly to Postgres or the model. The model never talks directly to the
client or database.

### Optional read-only agent (per request)

`POST /v1/agent-query` returns the same response shape as `/v1/query`. The difference is that the
model, not the server, writes the search text. Code: `src/secure_rag_demo/agent.py`.

1. The client sends a question and bearer token to `POST /v1/agent-query`. Validation and token
   to `Principal` mapping are identical to the query route.
2. FastAPI starts a 30-second deadline and asks the model for a tool call. The model is offered
   exactly one function, `search_documents(question)`, with `tool_choice="required"`. This first
   model call receives no source text.
3. The server validates the model's reply: exactly one call, the name `search_documents`,
   arguments at most 10,000 characters and matching a strict schema (one non-blank `question`
   string of at most 2,000 characters, no extra fields). Anything else raises `AgentToolError`.
4. FastAPI embeds the model's search text locally and sets PostgreSQL's `statement_timeout` to the
   remaining time.
5. FastAPI calls the existing `search_chunks` service once. The visibility predicate comes from the
   server-side principal, never from the model, and still runs in SQL before ranking.
6. FastAPI calls the existing `answer_question` with the user's **original** question and the
   authorized chunks. Redaction, the untrusted-source prompt, the reminder, the
   `INSUFFICIENT_EVIDENCE` gate and citations all work exactly as on the query route.
7. If tracing is enabled, FastAPI records metadata only: request ID, principal label, citation
   count, model, duration and outcome (`answered`, `abstained`, `agent_error` or `db_error`).
8. FastAPI returns the answer and citations, or an abstention. An invalid tool call, timeout,
   provider error or database error returns a generic 503.

| | `/v1/query` | `/v1/agent-query` |
|---|---|---|
| Who writes the search text | Server (the user's question) | Model (via one tool call) |
| Model calls per request | 1 | 2 (tool call, then answer) |
| Tools offered to the model | None | `search_documents` only |
| Database searches | 1 | Exactly 1 |
| Role filter | SQL, from server principal | Same SQL, same principal |
| Question used for the final answer | User's question | User's original question |
| Deadline | Provider timeout | 30 s total, including SQL statement timeout |
| Failure response | 503 | 503 (also for invalid tool calls) |

The agent exposes no write, browser, URL-fetch, or arbitrary network tool. Its trusted chat
provider still receives the normal model request at the configured endpoint (localhost Ollama by
default). A 30-second deadline bounds provider calls and sets PostgreSQL's statement timeout for
retrieval. The agent cannot change the role or bypass SQL authorization.

## Trust boundaries and controls

- **Client -> API:** HTTP request is untrusted; Pydantic bounds question length and rejects blanks.
- **API -> database:** SQL uses the server-resolved visibility set. The query path is read-only.
- **Retrieved documents -> model:** source text is untrusted and may contain prompt injection.
  Defences: ingestion screening, answer-time redaction of instruction-like sentences, `<sources>`
  tag neutralisation, the system prompt and a reminder after the question. The standard query
  route exposes no tools; the optional agent exposes only the single retrieval tool described above.
- **Model tool call -> API (agent only):** the model's tool call is untrusted output. The server
  checks name, count, size and schema before acting, and the model cannot choose role, limit,
  table or SQL. The worst a manipulated tool call can do is search for different text within the
  caller's own visibility.
- **API -> model provider:** localhost is the default. Hosted use is opt-in and limited to public
  demo content.
- **API -> telemetry:** tracing is opt-in, inputs and outputs are hidden, and the payload contains
  metadata only.
- **Demo identity:** static tokens are educational examples, not production authentication.

## Testing and verification

Verification has three layers. Each covers different risks; passing all of them is evidence for
specific controls, not proof of security. The "What runs" column describes how each layer is
designed to execute; the "Status" column records whether it actually has.

| Layer | What runs | Needs | Verifies | Status |
|---|---|---|---|---|
| 1. Automated tests | `uv run pytest -q` (also in CI with Ruff and mypy) | Postgres only; fake model and embedder | Security controls, deterministically | Run; 96 passed, 1 skipped |
| 2. Evaluation set | `uv run python -m evals.evaluate` | Running API, Ollama, ingested sources | Citations and abstention on 28 Swedish questions | Run; 28/28 on three consecutive runs (query); 28/28 on two runs (agent, `--endpoint agent`) |
| 3. Promptfoo probes | `uv run python -m security.canaries`, then `npx promptfoo eval -c security/promptfoo-static.yaml` | Running API, local DB, Ollama app model | Prompt injection, role bypass, leakage and abstention | 32/32 (16 per endpoint: query and agent); residual risk remains |

### Layer 1: automated tests

| Control | Test file |
|---|---|
| Missing or invalid token returns 401 | `tests/test_auth.py`, `tests/test_query_api.py` |
| Visibility filter excludes restricted chunks, even when they are the best match | `tests/test_retrieval.py`, `tests/test_query_api.py` |
| Citations derive only from retrieved chunks; empty retrieval abstains without a model call | `tests/test_answering.py` |
| Retrieved text is marked untrusted and the system prompt warns against source instructions | `tests/test_answering.py` |
| Invalid input returns 422; database and provider failures return 503 without internal details | `tests/test_query_api.py` |
| Traces carry metadata only; marker strings in question, chunk and answer never appear | `tests/test_tracing.py` |
| Tracing is off by default and LangSmith receives the hide settings | `tests/test_tracing.py` |
| Promptfoo target refuses non-loopback URLs and requires a token | `tests/test_promptfoo_target.py` |
| Synthetic canaries seed repeatably, enforce visibility, and remove only themselves | `tests/test_canaries.py` |
| Agent exposes one retrieval tool, performs at most one retrieval, enforces deadline and role, and does not write or open network connections from its tool path | `tests/test_agent.py` |

### Layer 2: evaluation set

`evals/public_questions.jsonl` contains 23 supported questions (covering all eight sources) and 5
unsupported questions. The evaluator
checks that supported answers cite the expected `source_url` from `evals/sources.json`, and that
unsupported questions return `abstained: true`, a null answer and no citations. Ingestion must use
the exact URLs in `evals/sources.json`. The live run returned the expected citation for all 23
supported cases, and all 5 unsupported cases abstain via the answerability gate; see
[evaluation results](evaluation.md).

### Layer 3: Promptfoo security probes

The hand-written suite in `security/promptfoo-static.yaml` sends explicit attack questions to the
loopback API and checks the JSON response with deterministic assertions; it has no generated
probes or model grader. Before the run, `security.canaries` inserts a synthetic poisoned public
page and a synthetic restricted document, and verifies they are retrievable only by the intended
principal. Remove these temporary documents after the run.

The first run found that local Ollama `llama3.1` followed the poisoned page's instruction: four
probes returned `POISON-CANARY-4417` (10/14 passed). The fix added three deterministic layers: (1) ingestion refuses documents matching instruction-like
patterns (`SuspectedInjectionError`) unless explicitly allowed; (2) at answer time, sentences
matching those patterns are replaced with `[removed: suspected instruction]` and `<sources>` tags
inside source text are neutralised; (3) a short reminder follows the question. The patterns are
in `src/secure_rag_demo/injection.py` and flag none of the eight real sources.
A third canary uses a paraphrased instruction (`POISON-CANARY-7730`) that the patterns deliberately
miss, to measure what remains. The expanded suite passed 16/16 on two runs. It now runs every probe against both
`/v1/query` and `/v1/agent-query` (two Promptfoo providers); the latest run passed 32/32. The result is specific
to this corpus and model and does not establish a general attack success rate.

An optional generated red-team config, `security/promptfoo.yaml`, retains the local `pii:direct`
and `rbac` plugins. Plugins that require cloud generation have been removed. A local generated
run produced 20 cases. On re-running them after the fix, the API abstained on all 20; the 18
failures reported by the local llama3.1 grader were triaged as grader false positives.
The static suite requires no cloud generation, model grader, or result sharing. `npx` may download
Promptfoo from the package registry. The target accepts only loopback HTTP and reads one bearer
token per run; the target cannot itself add documents or compare roles in a single run.

### Current status

- **Layer 1:** executed; 101 tests pass and 1 is skipped. Ruff and mypy pass locally.
- **Layer 2:** executed; 28/28 cases pass on three consecutive runs against `/v1/query`, and
  28/28 on two runs against `/v1/agent-query`.
- **Layer 3:** prompt injection found (10/14), mitigated, and re-tested: 16/16 on two runs,
  including the evasive canary; later 32/32 across the query and agent endpoints. Residual model-level risk remains. See
  [evaluation results](evaluation.md).

## Deliberate limitations

This prototype has no production identity provider, rate limiting, encryption-at-rest policy,
high availability, or independent answer-claim verifier. The answerability gate relies on the
LLM obeying an instruction, not on a separate classifier. An LLM can still produce unsupported
text despite the grounding prompt. Passing tests is evidence
for specific controls, not proof that the system is secure.

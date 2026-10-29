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
- **LangSmith (optional)** receives operational metadata only. Tracing is disabled by default.

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

## Trust boundaries and controls

- **Client -> API:** HTTP request is untrusted; Pydantic bounds question length and rejects blanks.
- **API -> database:** SQL uses the server-resolved visibility set. The query path is read-only.
- **Retrieved documents -> model:** source text is untrusted and may contain prompt injection.
  Defences: ingestion screening, answer-time redaction of instruction-like sentences, `<sources>`
  tag neutralisation, the system prompt and a reminder after the question; no tools are exposed.
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
| 1. Automated tests | `uv run pytest -q` (also in CI with Ruff and mypy) | Postgres only; fake model and embedder | Security controls, deterministically | Run; passing |
| 2. Evaluation set | `uv run python -m evals.evaluate` | Running API, Ollama, ingested sources | Citations and abstention on 28 Swedish questions | Run; 28/28 on three consecutive runs |
| 3. Promptfoo probes | `uv run python -m security.canaries`, then `npx promptfoo eval -c security/promptfoo-static.yaml` | Running API, local DB, Ollama app model | Prompt injection, role bypass, leakage and abstention | 10/14; prompt-injection finding |

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
miss, to measure what remains. The expanded suite passed 16/16 on two runs. The result is specific
to this corpus and model and does not establish a general attack success rate.

An optional generated red-team config, `security/promptfoo.yaml`, retains the local `pii:direct`
and `rbac` plugins. Plugins that require cloud generation have been removed. A local generated
run produced 20 cases. On re-running them after the fix, the API abstained on all 20; the 18
failures reported by the local llama3.1 grader were triaged as grader false positives.
The static suite requires no cloud generation, model grader, or result sharing. `npx` may download
Promptfoo from the package registry. The target accepts only loopback HTTP and reads one bearer
token per run; the target cannot itself add documents or compare roles in a single run.

### Current status

- **Layer 1:** executed; 84 tests pass and 1 is skipped. Ruff and mypy pass locally.
- **Layer 2:** executed; 28/28 cases pass on three consecutive runs.
- **Layer 3:** prompt injection found (10/14), mitigated, and re-tested: 16/16 on two runs,
  including the evasive canary. Residual model-level risk remains. See
  [evaluation results](evaluation.md).

## Deliberate limitations

This prototype has no production identity provider, rate limiting, encryption-at-rest policy,
high availability, or independent answer-claim verifier. The answerability gate relies on the
LLM obeying an instruction, not on a separate classifier. An LLM can still produce unsupported
text despite the grounding prompt. Passing tests is evidence
for specific controls, not proof that the system is secure.

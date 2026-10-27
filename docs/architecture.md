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
  The system prompt instructs the model not to follow source instructions; no tools are exposed.
- **API -> model provider:** localhost is the default. Hosted use is opt-in and limited to public
  demo content.
- **API -> telemetry:** tracing is opt-in, inputs and outputs are hidden, and the payload contains
  metadata only.
- **Demo identity:** static tokens are educational examples, not production authentication.

## Testing and verification

Verification has three layers. Each covers different risks; passing all of them is evidence for
specific controls, not proof of security.

| Layer | What runs | Needs | Verifies |
|---|---|---|---|
| 1. Automated tests | `uv run pytest -q` (also in CI with Ruff and mypy) | Postgres only; fake model and embedder | Security controls, deterministically |
| 2. Evaluation set | `uv run python -m evals.evaluate` | Running API, Ollama, ingested sources | Citations and abstention on 13 Swedish questions |
| 3. Promptfoo red team | `npx promptfoo redteam run -c security/promptfoo.yaml` | Running API, Ollama | Resistance to generated attack prompts |

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

### Layer 2: evaluation set

`evals/public_questions.jsonl` contains 10 supported and 3 unsupported questions. The evaluator
checks that supported answers cite the expected `source_url` from `evals/sources.json`, and that
unsupported questions return `abstained: true`, a null answer and no citations. Ingestion must use
the exact URLs in `evals/sources.json`.

### Layer 3: Promptfoo red team

Promptfoo acts as an automated attacker. It generates attack prompts with an LLM, sends them to
the API through `security/promptfoo_target.py`, grades each reply with an LLM, and reports pass or
fail. Plugins: `indirect-prompt-injection`, `pii:direct`, `rbac` and `rag-document-exfiltration`,
with the `jailbreak-templates` strategy.

Boundaries of this layer:
- **Local generation:** `redteam.provider` is local Ollama (`llama3.1`).
  `PROMPTFOO_DISABLE_REMOTE_GENERATION=true` disables Promptfoo's cloud probe generation and
  `PROMPTFOO_DISABLE_SHARING=true` prevents uploading results. Downloading Promptfoo via `npx`
  still needs the network, and Promptfoo telemetry is not disabled.
- **Loopback only:** the target accepts only `http` on `127.0.0.1`, `localhost` or `::1`.
- **No corpus poisoning:** the target sends only `{"question": ...}`. Promptfoo cannot insert a
  malicious document, so document-borne injection is primarily verified by Layer 1.
- **One role per run:** each run uses one `PROMPTFOO_BEARER_TOKEN`, so cross-role separation is
  primarily verified by Layer 1.

### Current status

Layer 1 passes locally. Layers 2 and 3 have not been run live yet because the public sources are
not ingested. Results and limitations will be recorded in [evaluation.md](evaluation.md).

## Deliberate limitations

This prototype has no production identity provider, rate limiting, encryption-at-rest policy,
high availability, calibrated semantic abstention threshold, or independent answer-claim verifier.
An LLM can still produce unsupported text despite the grounding prompt. Passing tests is evidence
for specific controls, not proof that the system is secure.

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

## Deliberate limitations

This prototype has no production identity provider, rate limiting, encryption-at-rest policy,
high availability, calibrated semantic abstention threshold, or independent answer-claim verifier.
An LLM can still produce unsupported text despite the grounding prompt. Passing tests is evidence
for specific controls, not proof that the system is secure.

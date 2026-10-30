# Interview demo script

## Before the demo

- Start Postgres, Ollama, and the API on loopback.
- Ingest only reviewed public documents and note their URLs/versions.
- Run `uv run pytest -q`; show the SQL access-filter and trace-redaction tests.
- Use the public demo token. Do not demonstrate with sensitive or private data.

## Demo (about five minutes)

1. **Frame the project:** this is a local educational prototype, not an agency system or classified
   environment.
2. **Show the flow:** a client sends a question and bearer token to FastAPI. The server resolves
   the principal, embeds the question locally, filters visibility in SQL, sends permitted chunks
   to an untrusted-context-aware prompt, and returns citations or abstention.
3. **Ask a supported question:** show the answer and source citation; open the cited public page.
4. **Ask an unsupported question:** show `abstained: true`, null answer, and no citations.
5. **Show access control:** explain how the public role cannot retrieve `restricted_demo` content;
   show `tests/test_retrieval.py` and `tests/test_query_api.py`.
6. **Show observability:** show `trace_query` and `tests/test_tracing.py`. The trace contains
   operational metadata, not request or answer content.
7. **Show the optional agent:** send the same supported question to `POST /v1/agent-query`.
   Explain that the model chooses the search text through one allowlisted tool, while the server
   keeps the role, validates the tool call and runs one SQL-filtered search. Show `test_agent.py`.
8. **Show evaluation:** show the public question set and Promptfoo config (both run against the query
   and agent endpoints), and the documented limitations.

## Svenska sammanfattningen

Jag byggde en lokal, skrivskyddad RAG-demonstration med FastAPI, PostgreSQL/pgvector och lokala
embeddings. Den visar hur man kan separera inläsning, autentisering, behörighetsfiltrering,
hämtning, modellåtkomst och spårning. Behörighetsfiltret tillämpas i SQL före rangordning.
Systemet returnerar källhänvisningar eller avstår när det saknas underlag. Automatiska tester
kontrollerar bland annat åtkomstgränser, felhantering och att känslig fråge- och svarstext inte
hamnar i spårningen. Det är ett utbildningsprojekt med offentlig testdata, inte ett system för
hemliga uppgifter.

## English summary

I built a local, read-only RAG demonstration using FastAPI, PostgreSQL/pgvector, and local
embeddings. It separates ingestion, authentication, authorization filtering, retrieval, model
access, and tracing. The authorization predicate is applied in SQL before ranking. The API returns
citations or abstains when it has no evidence. Automated tests cover access boundaries, error
handling, and metadata-only tracing. This is a learning project using public test data, not a
system for classified information.

# Local runbook

## Start

1. Copy `.env.example` to `.env`; keep demo values local and do not reuse real credentials.
2. Start Docker Desktop or Colima, then `docker compose up -d db`.
3. Run `uv sync --locked` and `uv run alembic upgrade head`.
4. Start local Ollama separately and pull the model named in `LLM_MODEL`, or configure an explicitly
   approved compatible provider for public demo data only.
5. Add reviewed public documents using `data/sources/README.md` and the ingestion CLI.
6. Start the API: `uv run uvicorn secure_rag_demo.main:app --host 127.0.0.1 --port 8000`.
7. Check `curl http://127.0.0.1:8000/healthz`.

## Verify

- `uv run ruff check .`
- `uv run mypy src evals security`
- `uv run pytest -q`
- Optional real embedding download: `RUN_MODEL_SMOKE=1 uv run pytest tests/test_embeddings_smoke.py -q`
- Optional local API evaluation: set `EVAL_BEARER_TOKEN` to a demo token and run
  `uv run python -m evals.evaluate`.
- Optional read-only agent smoke test: call `POST /v1/agent-query` with a demo bearer token.
  The agent offers only one role-filtered retrieval tool; the configured chat provider still
  receives the model request.
- Optional security probes: seed synthetic canaries, set `PROMPTFOO_BEARER_TOKEN` to the public
  demo token, and run the README Promptfoo command. Always remove the canaries afterward; the
  recorded run after the injection fix passed 16/16; with the agent endpoint added, 32/32. If `ingest_cli` prints `refused: suspected
  prompt injection`, review the document; do not bypass the check for real sources.

## Provider outage

Check `/healthz`, database status (`docker compose ps`), and local provider availability. The
health route checks only the process; it does not prove that the database or model is healthy.
Query errors should be generic 503 responses. Do not paste questions, retrieved text, tokens, or
provider credentials into issue trackers or traces. Restore the provider and retry with public
demo questions.

## Suspected token exposure

Stop the API, replace the local demo token in `.env`, restart the API, and remove any accidental
copy from logs or shell history. These static tokens are not designed for production revocation or
identity management.

## Suspected content or trace leakage

Stop the API and tracing immediately (`LANGSMITH_TRACING=false`). Preserve only necessary
metadata, not prompts or source contents. Check the trace payload tests before re-enabling
telemetry. Do not upload sensitive data for debugging.

## Shutdown and cleanup

Stop the API with Ctrl-C and stop the database using `docker compose down`. `docker compose down
-v` deletes the local database volume; use it only when intentionally resetting the demo corpus.
No service should be exposed on a public interface.

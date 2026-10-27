# Evaluation and security testing

## Deterministic checks

`uv run pytest -q` checks token handling, SQL access filtering, response citations, abstention,
request bounds, generic provider/database errors, and metadata-only tracing. These tests use fake
model and embedder implementations and do not call an external model.

`evals/public_questions.jsonl` contains ten supported Swedish public-information questions and
three unsupported questions. `evals/sources.json` maps stable source IDs to official URLs. With the
API running and those sources ingested, run:

```bash
EVAL_BEARER_TOKEN=demo-public-token-change-me uv run python -m evals.evaluate
```

The evaluator checks expected source citations and requires unsupported cases to abstain without
answer text or citations. It does not grade factual correctness, citation entailment, or answer
quality. Review results against the source pages.

## Promptfoo probes

Promptfoo sends adversarial questions only to `127.0.0.1`. The Python target refuses non-loopback
URLs and reads its token from `PROMPTFOO_BEARER_TOKEN`. Sharing is disabled for runs:

```bash
PROMPTFOO_DISABLE_SHARING=true \
PROMPTFOO_DISABLE_REMOTE_GENERATION=true \
PROMPTFOO_BEARER_TOKEN=demo-public-token-change-me \
npx promptfoo redteam run -c security/promptfoo.yaml
```

The configuration uses local Ollama (`llama3.1`) for attack generation and grading, and the command
disables remote generation and result sharing.

The configuration validates with Promptfoo 0.125.1. A live red-team scan has not yet been run:
the local Ollama server is not running and the selected source pages have not yet been ingested.
Start the model and API and add the reviewed public corpus before recording live results.

The configured indirect-injection and document-exfiltration plugins may not fully exercise
retrieved-document poisoning: the scanner sends requests through the query API and cannot insert
test documents into the database. The prompt-injection unit test is deterministic. RBAC behavior is
most directly proved by the public/restricted retrieval tests, because a single Promptfoo target
uses one bearer token per run.

## Recording results

Record Promptfoo version, Python/package lock, embedding model, LLM/provider/model, corpus source
URLs and versions, test commands, date, pass/fail counts, and limitations in a local report before
making claims. Do not commit generated outputs containing prompts or tokens. The `security/results/`
and `evals/results/` folders are git-ignored. Promptfoo results are evidence about tested cases,
not proof that the system is secure.

## Optional LangSmith experiment

Tracing and dataset upload remain opt-in. Before an upload, review every dataset item and expected
answer to ensure it is public. Verify the configured LangSmith project and hide settings. Never
upload private questions, source text, answers, tokens, or FRA material.

# Evaluation and security testing

## Deterministic checks

`uv run pytest -q` checks token handling, SQL access filtering, response citations, abstention,
request bounds, generic provider/database errors, and metadata-only tracing. These tests use fake
model and embedder implementations and do not call an external model.

`evals/public_questions.jsonl` contains 23 supported Swedish public-information questions, covering
all eight sources, and five unsupported questions. `evals/sources.json` maps stable source IDs to
official URLs. `tests/test_evaluation.py` checks that every expected source is registered and that
every registered source has at least one supported question. With the API running and those
sources ingested, run:

```bash
EVAL_BEARER_TOKEN=demo-public-token-change-me uv run python -m evals.evaluate
```

The evaluator checks expected source citations and requires unsupported cases to abstain without
answer text or citations. It does not grade factual correctness, citation entailment, or answer
quality. Review results against the source pages.

### Retrieval-only check (2026-10-27)

With the eight sources ingested (78 chunks, `intfloat/multilingual-e5-small`), each question was
embedded and passed to `search_chunks` with the public principal; no LLM was called. All 23
supported questions ranked a chunk from the expected source first (cosine distance 0.076–0.175).

Finding: the five unsupported questions also retrieved chunks, at distances of 0.122–0.184. That
overlaps the supported range, so the API will not abstain on them: it only abstains when retrieval
returns nothing. A distance threshold alone would not separate the two groups.

### Live API evaluation (2026-10-27)

Ran the 28 cases against the local API, Ollama `llama3.1`, and the eight-source/78-chunk corpus:
**23/28 passed**. All 23 supported cases returned a non-empty answer with the expected source
citation. All five unsupported cases failed: each returned citations and `abstained: false`.
This confirms the retrieval-only finding. The API needs an answerability check before it can meet
the dataset's unsupported-question expectation; the current evaluator does not treat a natural
language refusal from the model as abstention.

### Role-isolation smoke test

Temporarily ingested one synthetic `restricted_demo` marker and queried the live API with both
demo tokens. The public principal did not cite the restricted source; the restricted principal
did. The temporary document was removed afterward, and the corpus returned to 8 documents and
78 chunks. This verifies the server-side visibility filter end to end using synthetic text, not
classified or private data.

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

Promptfoo 0.125.1 ran locally against the API on 2026-10-27. Test generation requested 40 cases,
but produced 20: 5 `pii:direct`, 5 `rbac`, and 10 `jailbreak-templates` cases. The
`indirect-prompt-injection` and `rag-document-exfiltration` plugins each failed to generate their
five cases because they require remote generation, which was explicitly disabled. All 20
generated probes passed (20/20; scan duration 1m 52s). Treat this as a partial scan, not a pass
for all configured plugins. The run used local Ollama `llama3.1`; result sharing and remote
generation were disabled.

The configured indirect-injection and document-exfiltration plugins may not fully exercise
retrieved-document poisoning: the scanner sends requests through the query API and cannot insert
test documents into the database. The prompt-injection unit test is deterministic. RBAC behavior is
most directly proved by the public/restricted retrieval tests, because a single Promptfoo target
uses one bearer token per run.

The automated checks also pass locally: `uv run pytest -q` reports 47 passed and 1 skipped;
`uv run ruff check .` and `uv run mypy src` are clean.

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

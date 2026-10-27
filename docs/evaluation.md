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

### Answerability gate

Retrieval always returns the nearest chunks, even for questions the corpus cannot answer. A
retrieval-only check showed that the cosine distances overlap: 0.076–0.175 for supported questions
and 0.122–0.184 for unsupported ones. A distance threshold therefore cannot separate them.

The system prompt now tells the model to reply with exactly `INSUFFICIENT_EVIDENCE` when the
sources do not state the answer, or when the question asks about a specific private person.
`answer_question` treats any reply containing that sentinel as an abstention: no answer, no
citations, `abstained: true`. This fails safe, because an injected or confused reply that mentions
the sentinel can only cause a refusal, never a leak. The gate relies on the model following
instructions; it is not a separate classifier.

### Live API evaluation (2026-10-27)

Setup: local API, Ollama `llama3.1` at temperature 0, `intfloat/multilingual-e5-small`, and eight
public sources (73 chunks). Provenance headers are stripped before ingestion, so licence notes are
not embedded.

| Run | Result | Notes |
|---|---|---|
| 1, before the gate | 23/28 | All five unsupported cases answered with citations |
| 2, gate only | 23/28 | All unsupported cases passed. Five supported cases abstained. |
| 3–5, gate, header stripping, corrected questions | 28/28 | Same result on three consecutive runs |

In run 2, three failures (`mcf-01`..`03`) were bad test data. Their answers were not in the saved
MCF landing page, which is only a link index; before the gate, the model had guessed. Those
questions were rewritten to match the page content. `mcf-odla-01`'s answer chunk was not in the
top five until the header noise was removed.

### Role-isolation smoke test

Temporarily ingested one synthetic `restricted_demo` marker document and queried the live API with
both demo tokens. The public principal abstained: no restricted citation, and the marker did not
appear in the answer. The restricted principal cited the document and returned the marker. The
temporary document was removed afterward (8 documents, 73 chunks). This verifies the server-side
visibility filter end to end, using synthetic text only.

## Promptfoo probes

Promptfoo sends adversarial questions only to `127.0.0.1`. The Python target refuses non-loopback
URLs and reads its token from `PROMPTFOO_BEARER_TOKEN`. Sharing is disabled for runs:

```bash
PROMPTFOO_DISABLE_SHARING=true \
PROMPTFOO_BEARER_TOKEN=demo-public-token-change-me \
npx promptfoo@0.125.1 redteam run -c security/promptfoo.yaml --force
```

Local Ollama (`llama3.1`) grades the replies and writes most probes. `indirect-prompt-injection`
and `rag-document-exfiltration` require Promptfoo's cloud generation, which receives the scan
`purpose` and plugin settings (no tokens). Promptfoo requires email verification before a scan
that uses cloud generation. Add `PROMPTFOO_DISABLE_REMOTE_GENERATION=true` for a fully local,
partial scan. Result sharing stays disabled.

**Local-only run (2026-10-27, before the answerability gate).** Promptfoo 0.125.1 requested 40 cases,
but produced 20: 5 `pii:direct`, 5 `rbac`, and 10 `jailbreak-templates` cases. The
`indirect-prompt-injection` and `rag-document-exfiltration` plugins each failed to generate their
five cases because they require remote generation, which was explicitly disabled. All 20
generated probes passed (20/20; scan duration 1m 52s). Treat this as a partial scan, not a pass
for all configured plugins. The run used local Ollama `llama3.1`; result sharing and remote
generation were disabled.

**Run with cloud generation:** pending. It needs interactive email verification.

The `indirect-prompt-injection` plugin puts its payload in a `context` variable. The target sends
only the question, so the payload never reaches the API, and passes from that plugin say nothing
about document-borne injection. That is covered by the deterministic unit test and the threat
model.

The configured indirect-injection and document-exfiltration plugins may not fully exercise
retrieved-document poisoning: the scanner sends requests through the query API and cannot insert
test documents into the database. The prompt-injection unit test is deterministic. RBAC behavior is
most directly proved by the public/restricted retrieval tests, because a single Promptfoo target
uses one bearer token per run.

The automated checks also pass locally: `uv run pytest -q` reports 53 passed and 1 skipped;
`uv run ruff check .` and `uv run mypy src evals security/promptfoo_target.py` are clean.

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

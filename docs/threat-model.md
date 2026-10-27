# Threat model

## System and security objectives

Protect local source text and role boundaries, prevent unauthorized retrieval, reduce prompt
injection and unsupported answers, avoid content leakage through traces and errors, and keep the
query path read-only.

## Assets

- Public source text and its attribution/version metadata.
- Visibility labels and demo bearer tokens.
- Retrieved chunks, questions, generated answers, and citations.
- Database integrity, service availability, and trace metadata.

No classified, private, or FRA information belongs in this demo.

## Trust boundaries

1. User/client to FastAPI.
2. FastAPI to PostgreSQL/pgvector.
3. Stored public content to the LLM prompt.
4. FastAPI to optional external LLM and optional LangSmith.
5. Local developer machine and its `.env`, Docker volumes, and model cache.

## STRIDE-style threats and controls

| Threat | Example | Controls and evidence | Residual risk |
|---|---|---|---|
| Spoofing | Caller supplies a privileged role or guesses a demo token | Server maps bearer tokens to immutable principals; constant-time comparison; 401 tests | Static educational tokens are not suitable for real users |
| Tampering | Malicious document instructions or modified source text | Sources are untrusted; content hash and URL/version attribution; prompt-injection tests | Prompt instructions do not guarantee model obedience |
| Repudiation | Cannot correlate an incident with a request | Random request ID and metadata-only trace | No durable local audit log when tracing is disabled |
| Information disclosure | Public role receives restricted-demo chunk; prompt appears in trace | Visibility predicate in SQL before ranking; response citations only; trace redaction tests | Application host/database access is outside this demo's auth boundary |
| Denial of service | Huge question or unavailable provider/database | 2,000-character input cap; provider timeout; 503 errors | No rate limit, queue, or resource isolation |
| Elevation of privilege | Prompt injection tells model to fetch other documents | No model tools/database access; authorization before retrieval; injection tests | Model may still produce misleading answers from allowed context |

## Abuse cases and expected behavior

- Missing/invalid token: return 401 without retrieval.
- Public principal asks for a restricted-demo chunk: SQL returns no restricted chunk.
- Retrieved text contains instructions: treat it as data, not authority; do not expose tools.
- No matching chunks: return `answer: null`, no citations, and `abstained: true`.
- Provider/database unavailable: return generic 503 without exception details.
- Trace exporter unavailable: log a generic warning and continue the query.

## Verification

Run `uv run pytest -q` for deterministic boundary checks. Run the Promptfoo configuration only
against the loopback API and public demo corpus. Review each generated probe and result; plugin
coverage does not replace the explicit tests above.

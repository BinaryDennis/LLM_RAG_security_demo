# Threat model

## System and security objectives

Protect local source text and role boundaries, prevent unauthorized retrieval, reduce prompt
injection and unsupported answers, avoid content leakage through traces and errors, and keep the
query and agent paths read-only.

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
6. LLM tool call to FastAPI (optional agent): the model's requested tool and arguments are
   untrusted output.

## STRIDE-style threats and controls

| Threat | Example | Controls and evidence | Residual risk |
|---|---|---|---|
| Spoofing | Caller supplies a privileged role or guesses a demo token | Server maps bearer tokens to immutable principals; constant-time comparison; 401 tests | Static educational tokens are not suitable for real users |
| Tampering | Malicious document instructions or modified source text | Sources are untrusted; ingestion screening; answer-time redaction; content hash and URL/version attribution; prompt-injection tests | Patterns are bypassable by paraphrase; prompt instructions do not guarantee model obedience |
| Repudiation | Cannot correlate an incident with a request | Random request ID and metadata-only trace | No durable local audit log when tracing is disabled |
| Information disclosure | Public role receives restricted-demo chunk; prompt appears in trace | Visibility predicate in SQL before ranking; response citations only; trace redaction tests | Application host/database access is outside this demo's auth boundary |
| Denial of service | Huge question or unavailable provider/database | 2,000-character input cap; provider timeout; agent 30-second deadline with PostgreSQL statement timeout and one search per request; 503 errors | No rate limit, queue, or resource isolation |
| Elevation of privilege | Prompt injection requests disallowed data or actions | Standard query gives the model no tools; optional agent exposes only one role-filtered retrieval tool, with no write or arbitrary network tools | Agent can still retrieve any document allowed to the caller; model may mislead about retrieved evidence |

## Abuse cases and expected behavior

- Missing/invalid token: return 401 without retrieval.
- Public principal asks for a restricted-demo chunk: SQL returns no restricted chunk.
- Retrieved text contains instructions: treat it as data, not authority; do not expose tools.
- No matching chunks: return `answer: null`, no citations, and `abstained: true`.
- Chunks retrieved but the model replies `INSUFFICIENT_EVIDENCE`: same abstention response. Any
  reply containing the sentinel abstains, so a manipulated reply can only cause a refusal.
- Provider/database unavailable: return generic 503 without exception details.
- Trace exporter unavailable: log a generic warning and continue the query.
- Agent model requests no tool, several tools, an unknown tool, or malformed/oversized
  arguments: return a generic 503 without searching.
- Agent model tries to search for restricted content: the SQL filter still uses the caller's
  server-side role, so nothing outside that visibility is returned.
- Agent request exceeds 30 seconds: stop and return a generic 503.

## Verification

Run `uv run pytest -q` for deterministic boundary checks. Run the Promptfoo configuration only
against the loopback API and public demo corpus. Review each generated probe and result; plugin
coverage does not replace the explicit tests above.

# Risk register

| ID | Risk | Initial severity | Control/evidence | Residual risk | Owner |
|---|---|---|---|---|---|
| R1 | Prompt injection in a public source manipulates answer | High | Untrusted-source prompt; no tools; synthetic canary probe | High until mitigated: local `llama3.1` followed the poisoned page instruction and emitted its marker in 4/14 probes | Demo maintainer |
| R2 | Unauthorized visibility data reaches generation | High | SQL visibility predicate before ranking; retrieval and API access tests | Low for tested path; database/operator access is not covered | Demo maintainer |
| R3 | Model states claims not supported by sources | High | Citation-only-from-retrieval contract, abstain on empty retrieval, `INSUFFICIENT_EVIDENCE` answerability gate, evaluation set (28/28) | Medium: gate depends on the LLM following instructions; no independent claim entailment verifier | Demo maintainer |
| R4 | Question, chunk, or answer is sent to tracing | High | Metadata-only trace payload, hidden input/output settings, seeded-marker test | Low for implemented trace path; external SDK behavior still needs review on upgrades | Demo maintainer |
| R5 | Demo token mistaken for production authentication | High | Explicit educational-only labels in config/docs | Medium: users can reuse weak static defaults | Demo maintainer |
| R6 | Hosted provider receives data unexpectedly | High | Local Ollama default; hosted provider requires explicit base URL configuration | Medium: operator may misconfigure endpoint or send non-public material | Demo maintainer |
| R7 | Public source text is redistributed without permission | Medium | Sources excluded from Git; record URL/version/reuse terms | Low if operator follows source instructions | Corpus curator |
| R8 | API or model outage disrupts demo | Low | Generic 503 handling and local runbook | Low for single-user demo; no HA or recovery automation | Demo maintainer |
| R9 | Promptfoo output is misread as proof of security | Medium | Report scope and limitations documented; unit tests remain primary evidence | Medium: automated probes are incomplete and model-dependent | Demo maintainer |

Severity is a qualitative prioritization for this learning prototype, not a formal organizational
risk assessment. Reassess after changing data, models, providers, or access controls.

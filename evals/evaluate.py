import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ENDPOINTS = {
    "query": "http://127.0.0.1:8000/v1/query",
    "agent": "http://127.0.0.1:8000/v1/agent-query",
}


def resolve_target_url(endpoint: str) -> str:
    return os.environ.get("SECURE_RAG_TARGET_URL") or ENDPOINTS[endpoint]


def evaluate_response(
    case: dict[str, Any], response: dict[str, object], source_ids: dict[str, str]
) -> list[str]:
    expected_abstained = case["expected_abstained"]
    expected_sources = set(case["expected_sources"])
    citations = response.get("citations", [])
    if not isinstance(citations, list):
        return ["citations is not a list"]
    actual_sources = {
        source_id
        for citation in citations
        if isinstance(citation, dict)
        for source_id, url in source_ids.items()
        if citation.get("source_url") == url
    }
    errors: list[str] = []
    if response.get("abstained") is not expected_abstained:
        errors.append("abstention did not match expected value")
    if expected_abstained:
        if response.get("answer") is not None or citations:
            errors.append("unsupported case must have null answer and no citations")
    else:
        answer = response.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            errors.append("supported case must have a non-empty answer")
        if not expected_sources.issubset(actual_sources):
            errors.append("one or more expected source citations are missing")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the public evaluation set.")
    parser.add_argument("--endpoint", choices=sorted(ENDPOINTS), default="query")
    args = parser.parse_args(argv)
    api_url = resolve_target_url(args.endpoint)
    parsed = urlparse(api_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        print("Evaluation target must use plain HTTP on loopback only.", file=sys.stderr)
        return 2
    token = os.environ.get("EVAL_BEARER_TOKEN")
    if not token:
        print("Set EVAL_BEARER_TOKEN to a local demo token.", file=sys.stderr)
        return 2

    source_ids: dict[str, str] = json.loads((ROOT / "sources.json").read_text())
    cases = [
        json.loads(line) for line in (ROOT / "public_questions.jsonl").read_text().splitlines()
    ]
    print(f"target: {api_url}")
    failures = 0
    for case in cases:
        req = Request(
            api_url,
            data=json.dumps({"question": case["question"]}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=90) as result:
                response = json.loads(result.read())
        except HTTPError as http_error:
            print(f"{case['id']}: FAIL (HTTP {http_error.code})")
            failures += 1
            continue
        except URLError:
            print(f"{case['id']}: FAIL (local API connection failed)")
            failures += 1
            continue
        errors = evaluate_response(case, response, source_ids)
        print(f"{case['id']}: {'PASS' if not errors else 'FAIL'}")
        for error in errors:
            print(f"  - {error}")
        failures += bool(errors)
    print(f"{len(cases) - failures}/{len(cases)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

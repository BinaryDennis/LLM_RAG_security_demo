import json
from pathlib import Path
from typing import Any

from evals.evaluate import evaluate_response

ROOT = Path(__file__).resolve().parents[1]


def _load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (ROOT / "evals/public_questions.jsonl").read_text().splitlines()
    ]


def _load_sources() -> dict[str, str]:
    sources: dict[str, str] = json.loads((ROOT / "evals/sources.json").read_text())
    return sources


def test_public_evaluation_dataset_counts_and_unique_ids() -> None:
    cases = _load_cases()
    assert len(cases) == 28
    assert sum(not case["expected_abstained"] for case in cases) == 23
    assert sum(case["expected_abstained"] for case in cases) == 5
    assert len({case["id"] for case in cases}) == len(cases)


def test_every_expected_source_is_registered() -> None:
    sources = _load_sources()
    for case in _load_cases():
        for source_id in case["expected_sources"]:
            assert source_id in sources, f"{case['id']} references unknown {source_id}"


def test_every_registered_source_has_a_supported_case() -> None:
    covered = {
        source_id
        for case in _load_cases()
        if not case["expected_abstained"]
        for source_id in case["expected_sources"]
    }
    assert covered == set(_load_sources())


def test_unsupported_cases_expect_no_sources() -> None:
    for case in _load_cases():
        if case["expected_abstained"]:
            assert case["expected_sources"] == []


def test_local_source_snapshots_are_registered() -> None:
    # Snapshots are git-ignored, so in CI this checks nothing.
    registered = set(_load_sources().values())
    for path in (ROOT / "data/sources").glob("*.md"):
        if path.name == "README.md":
            continue
        first_line = path.read_text().splitlines()[0]
        assert first_line.startswith("Source: "), path.name
        assert first_line.removeprefix("Source: ") in registered, path.name


def test_evaluator_accepts_expected_source_citation() -> None:
    case = {
        "expected_abstained": False,
        "expected_sources": ["imy_personuppgiftsincidenter"],
    }
    response = {
        "answer": "En personuppgiftsincident kan innebära obehörig åtkomst.",
        "abstained": False,
        "citations": [
            {
                "source_url": "https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/personuppgiftsincidenter/"
            }
        ],
    }
    sources = json.loads((ROOT / "evals/sources.json").read_text())
    assert evaluate_response(case, response, sources) == []


def test_evaluator_rejects_answer_for_unsupported_question() -> None:
    case = {"expected_abstained": True, "expected_sources": []}
    response = {"answer": "A guess", "abstained": False, "citations": []}
    assert evaluate_response(case, response, {}) == [
        "abstention did not match expected value",
        "unsupported case must have null answer and no citations",
    ]

import json
from pathlib import Path

from evals.evaluate import evaluate_response

ROOT = Path(__file__).resolve().parents[1]


def test_public_evaluation_dataset_has_ten_supported_and_three_unsupported() -> None:
    cases = [
        json.loads(line)
        for line in (ROOT / "evals/public_questions.jsonl").read_text().splitlines()
    ]
    assert len(cases) == 13
    assert sum(not case["expected_abstained"] for case in cases) == 10
    assert sum(case["expected_abstained"] for case in cases) == 3
    assert len({case["id"] for case in cases}) == len(cases)


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

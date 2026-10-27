from security.promptfoo_target import call_api


def test_promptfoo_target_refuses_non_loopback_url() -> None:
    result = call_api(
        "question",
        {"config": {"url": "https://example.com/v1/query"}},
        {},
    )
    assert result == {"error": "target must use plain HTTP on loopback only"}


def test_promptfoo_target_requires_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("PROMPTFOO_BEARER_TOKEN", raising=False)
    result = call_api(
        "question",
        {"config": {"url": "http://127.0.0.1:8000/v1/query"}},
        {},
    )
    assert result == {"error": "PROMPTFOO_BEARER_TOKEN is required"}

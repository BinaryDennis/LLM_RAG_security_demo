from typing import Self

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


def test_promptfoo_target_posts_to_configured_agent_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import security.promptfoo_target as target

    seen: list[str] = []

    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"answer": null}'

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        seen.append(request.full_url)
        return Response()

    monkeypatch.setenv("PROMPTFOO_BEARER_TOKEN", "tok")
    monkeypatch.delenv("SECURE_RAG_TARGET_URL", raising=False)
    monkeypatch.setattr(target, "urlopen", fake_urlopen)
    result = target.call_api(
        "question", {"config": {"url": "http://127.0.0.1:8000/v1/agent-query"}}, {}
    )
    assert result == {"output": '{"answer": null}'}
    assert seen == ["http://127.0.0.1:8000/v1/agent-query"]


def test_static_suite_targets_both_query_and_agent_endpoints() -> None:
    from pathlib import Path

    config = Path("security/promptfoo-static.yaml").read_text()
    assert "url: http://127.0.0.1:8000/v1/query" in config
    assert "url: http://127.0.0.1:8000/v1/agent-query" in config

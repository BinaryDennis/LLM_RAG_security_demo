import pytest
from fastapi import HTTPException

from secure_rag_demo.auth import resolve_principal
from secure_rag_demo.config import Settings

S = Settings(demo_token_public="tok-public", demo_token_restricted="tok-restricted")


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer wrong", "Basic tok-public"])
def test_missing_or_invalid_token_is_401(header: str | None) -> None:
    with pytest.raises(HTTPException) as exc:
        resolve_principal(header, S)
    assert exc.value.status_code == 401


def test_public_token_sees_only_public() -> None:
    p = resolve_principal("Bearer tok-public", S)
    assert p.allowed_visibility == frozenset({"public"})


def test_restricted_token_sees_public_and_restricted_demo() -> None:
    p = resolve_principal("Bearer tok-restricted", S)
    assert p.allowed_visibility == frozenset({"public", "restricted_demo"})

import hmac
from dataclasses import dataclass

from fastapi import HTTPException

from secure_rag_demo.config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    subject: str
    allowed_visibility: frozenset[str]


def resolve_principal(authorization: str | None, settings: Settings | None = None) -> Principal:
    """Map a bearer token to a role on the server. Educational demo auth only."""
    settings = settings or get_settings()
    unauthorized = HTTPException(status_code=401, detail="Unauthorized")
    if not authorization:
        raise unauthorized
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized

    candidates = (
        (settings.demo_token_public, Principal("demo-public", frozenset({"public"}))),
        (
            settings.demo_token_restricted,
            Principal("demo-restricted", frozenset({"public", "restricted_demo"})),
        ),
    )
    match: Principal | None = None
    for expected, principal in candidates:
        # compare every candidate so timing does not reveal which token matched
        if hmac.compare_digest(token.encode(), expected.encode()):
            match = principal
    if match is None:
        raise unauthorized
    return match

from fastapi.testclient import TestClient

from secure_rag_demo.api import create_app


def test_healthz_returns_ok() -> None:
    response = TestClient(create_app()).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from optiagent_agent.testing import FakeLLM
from optiagent_api.main import app
from optiagent_api.routers.agent import get_llm
from optiagent_api.security import SlidingWindowLimiter
from optiagent_api.settings import Settings, get_settings

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def strict_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    import optiagent_api.security as security

    settings = Settings(requests_per_minute=5, llm_requests_per_hour=2, max_request_bytes=1_000)
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    yield settings
    app.dependency_overrides.clear()


def test_limiter_window() -> None:
    limiter = SlidingWindowLimiter()
    assert limiter.hit("k", 2, 60) is None
    assert limiter.hit("k", 2, 60) is None
    wait = limiter.hit("k", 2, 60)
    assert wait is not None and 0 < wait <= 60
    assert limiter.hit("other", 2, 60) is None


def test_security_headers_and_request_id() -> None:
    response = client.get("/api/v1/examples")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert len(response.headers["x-request-id"]) == 32
    echoed = client.get("/health", headers={"x-request-id": "abc12345trace"})
    assert echoed.headers["x-request-id"] == "abc12345trace"


def test_per_ip_rate_limit(strict_settings: Settings) -> None:
    codes = [client.get("/api/v1/examples").status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert codes[5:] == [429, 429]
    assert client.get("/health").status_code == 200  # health checks are never limited


def test_llm_rate_limit(strict_settings: Settings) -> None:
    reply = {"kind": "assignment", "summary": "s", "requirements": [], "questions": []}
    app.dependency_overrides[get_llm] = lambda: FakeLLM(reply, reply, reply)
    codes = [client.post("/api/v1/agent/analyze", json={"text": "x"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_oversized_request_is_rejected(strict_settings: Settings) -> None:
    response = client.post(
        "/api/v1/solve", content=b"x" * 2_000, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_unhandled_errors_do_not_leak_details() -> None:
    boom = APIRouter()

    @boom.get("/api/v1/_boom")
    def explode() -> None:
        raise RuntimeError("secret internal detail")

    app.include_router(boom)
    response = client.get("/api/v1/_boom")
    assert response.status_code == 500
    body = response.json()
    assert "secret" not in response.text
    assert body["request_id"]

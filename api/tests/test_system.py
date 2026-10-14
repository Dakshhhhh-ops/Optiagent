from fastapi.testclient import TestClient
from optiagent_api.main import app
from optiagent_api.settings import Settings, get_settings

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_reports_unreachable_services() -> None:
    # Point everything at a closed port so the test never depends on local services.
    app.dependency_overrides[get_settings] = lambda: Settings(
        ollama_base_url="http://127.0.0.1:1",
        postgres_port=1,
        redis_port=1,
    )
    try:
        response = client.get("/api/v1/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["ollama"]["reachable"] is False
    assert {s["name"] for s in body["services"]} == {"postgres", "redis"}
    assert all(not s["reachable"] for s in body["services"])

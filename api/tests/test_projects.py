from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from optiagent_api.main import app
from optiagent_api.projects import ProjectStore
from optiagent_api.routers.projects import get_projects

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(engine: Engine) -> Iterator[None]:
    store = ProjectStore(engine)
    app.dependency_overrides[get_projects] = lambda: store
    yield
    app.dependency_overrides.clear()


def example(example_id: str) -> dict[str, object]:
    return client.get(f"/api/v1/examples/{example_id}").json()["problem"]  # type: ignore[no-any-return]


def test_create_solves_on_the_server_and_lists() -> None:
    created = client.post(
        "/api/v1/projects",
        json={
            "problem": example("t2_sunray"),
            "source": "ai",
            "description": "Ship grain from three silos to four mills at the lowest cost please",
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Ship grain from three silos to four mills…"
    assert project["objective"] == 435
    assert project["verified"] is True
    assert project["report"]["insights"]

    listed = client.get("/api/v1/projects").json()
    assert [p["id"] for p in listed] == [project["id"]]
    assert "report" not in listed[0]

    fetched = client.get(f"/api/v1/projects/{project['id']}").json()
    assert fetched["problem"]["kind"] == "transportation"
    assert fetched["report"]["result"]["objective"] == 435


def test_rename_and_delete() -> None:
    project = client.post(
        "/api/v1/projects", json={"problem": example("a1_three_by_three"), "source": "manual"}
    ).json()
    assert project["name"] == "Three workers, three jobs"

    renamed = client.patch(f"/api/v1/projects/{project['id']}", json={"name": "  Shop floor  "})
    assert renamed.json()["name"] == "Shop floor"

    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 404


def test_infeasible_project_is_saved_with_diagnosis() -> None:
    project = client.post(
        "/api/v1/projects",
        json={"problem": example("x1_infeasible_short_supply"), "source": "manual"},
    ).json()
    assert project["status"] == "infeasible"
    assert project["verified"] is False
    assert project["report"]["diagnosis"]["total_shortfall"] == 10

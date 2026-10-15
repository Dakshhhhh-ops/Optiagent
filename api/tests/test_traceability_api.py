from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from optiagent_api.datasets import DatasetStore
from optiagent_api.main import app
from optiagent_api.projects import ProjectStore
from optiagent_api.routers.datasets import get_store
from optiagent_api.routers.projects import get_projects

client = TestClient(app)

TEXT = (
    "Plant A has 30 units and Plant B has 20 units. Store X needs 25 units and Store Y needs "
    "25 units. Shipping from Plant A to Store X costs 4, Plant A to Store Y costs 6, Plant B to "
    "Store X costs 5 and Plant B to Store Y costs 3. Minimize the total shipping cost."
)
PROBLEM = {
    "kind": "transportation",
    "sources": [{"id": "Plant A", "supply": 30}, {"id": "Plant B", "supply": 20}],
    "destinations": [{"id": "Store X", "demand": 25}, {"id": "Store Y", "demand": 25}],
    "routes": [
        {"source": "Plant A", "destination": "Store X", "cost": 4},
        {"source": "Plant A", "destination": "Store Y", "cost": 6},
        {"source": "Plant B", "destination": "Store X", "cost": 5},
        {"source": "Plant B", "destination": "Store Y", "cost": 3},
    ],
}


@pytest.fixture(autouse=True)
def isolated(engine: Engine) -> Iterator[None]:
    projects = ProjectStore(engine)
    datasets = DatasetStore(engine, max_file_bytes=1_000_000, max_files=5)
    app.dependency_overrides[get_projects] = lambda: projects
    app.dependency_overrides[get_store] = lambda: datasets
    yield
    app.dependency_overrides.clear()


def _create(**body: object) -> dict[str, object]:
    response = client.post("/api/v1/projects", json={"source": "ai", **body})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_traceability_endpoint_needs_no_ai() -> None:
    report = client.post("/api/v1/traceability", json={"problem": PROBLEM, "text": TEXT}).json()
    assert report["status"] == "checked"
    assert report["counts"]["unresolved"] == 0


def test_saved_project_records_formulation_status_separately_from_verification() -> None:
    wrong = {**PROBLEM, "sense": "maximize"}
    project = _create(problem=wrong, description=TEXT)
    # The plan is a correct optimum of the model it was given...
    assert project["verified"] is True
    # ...but the model does not match the description, and that is recorded.
    assert project["formulation_status"] == "needs_review"
    listed = client.get("/api/v1/projects").json()
    assert listed[0]["formulation_status"] == "needs_review"


def test_unsupported_description_is_recorded() -> None:
    project = _create(
        problem=PROBLEM, description=TEXT + " Opening a plant has a fixed cost of 900."
    )
    assert project["formulation_status"] == "unsupported"


def test_file_provenance_is_rechecked_on_the_server() -> None:
    dataset_id = client.post("/api/v1/datasets/samples/sunray").json()["meta"]["id"]
    mapping = client.post(
        f"/api/v1/datasets/{dataset_id}/suggest", json={"kind": "transportation"}
    ).json()["mapping"]
    problem = client.post(f"/api/v1/datasets/{dataset_id}/build", json=mapping).json()["problem"]

    faithful = _create(problem=problem, dataset_id=dataset_id, mapping=mapping)
    trace = faithful["traceability"]
    assert {p["source"] for p in trace["provenance"]} == {"file"}
    assert faithful["formulation_status"] == "checked"

    edited = {**problem, "routes": [{**problem["routes"][0], "cost": 999}, *problem["routes"][1:]]}
    tampered = _create(problem=edited, dataset_id=dataset_id, mapping=mapping)
    assert tampered["formulation_status"] == "needs_review"
    assert tampered["traceability"]["requirements"][0]["method"] == "file_data"


def test_review_can_only_flag() -> None:
    review = {"checks": [{"requirement": "x", "status": "missing", "where": "", "reason": ""}]}
    project = _create(problem=PROBLEM, description=TEXT, requirements=["x"], review=review)
    assert project["formulation_status"] == "needs_review"

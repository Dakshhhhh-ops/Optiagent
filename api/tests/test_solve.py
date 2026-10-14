from fastapi.testclient import TestClient

from optiagent_api.main import app

client = TestClient(app)


def test_solve_transportation() -> None:
    problem = client.get("/api/v1/examples/t2_sunray").json()["problem"]
    response = client.post("/api/v1/solve", json=problem)
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "optimal"
    assert body["result"]["objective"] == 435
    assert body["verified"] is True
    assert body["verification"]["passed"] is True
    assert body["solution"]["kind"] == "transportation"
    assert body["stats"] == {"variables": 12, "constraints": 7, "nonzeros": 24, "is_mip": False}


def test_solve_assignment() -> None:
    problem = client.get("/api/v1/examples/a2_ta_labs_preferences").json()["problem"]
    body = client.post("/api/v1/solve", json=problem).json()
    assert body["result"]["objective"] == 17
    assert {(a["agent"], a["task"]) for a in body["solution"]["assignments"]} == {
        ("A", "L1"),
        ("D", "L1"),
        ("B", "L2"),
        ("C", "L2"),
    }


def test_solve_infeasible_reports_prechecks() -> None:
    problem = client.get("/api/v1/examples/x1_infeasible_short_supply").json()["problem"]
    body = client.post("/api/v1/solve", json=problem).json()
    assert body["result"]["status"] == "infeasible"
    assert body["solution"] is None
    failed = [c["name"] for c in body["prechecks"] if not c["passed"]]
    assert "supply_covers_demand" in failed


def test_invalid_problem_is_rejected() -> None:
    response = client.post(
        "/api/v1/solve",
        json={
            "kind": "transportation",
            "sources": [{"id": "S1", "supply": 1}],
            "destinations": [{"id": "D1", "demand": 1}],
            "routes": [{"source": "S9", "destination": "D1", "cost": 1}],
        },
    )
    assert response.status_code == 422
    assert "unknown source" in response.text


def test_examples_list() -> None:
    examples = client.get("/api/v1/examples").json()
    assert len(examples) >= 6
    assert client.get("/api/v1/examples/nope").status_code == 404

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from optiagent_agent.llm import LLMError, LLMReply, Message
from optiagent_agent.testing import FakeLLM
from optiagent_api.datasets import DatasetStore
from optiagent_api.main import app
from optiagent_api.routers.agent import get_llm
from optiagent_api.routers.datasets import get_store

client = TestClient(app)

TEXT = (
    "Two plants, P1 (20 units) and P2 (30 units), supply cities C1 (needs 25) and C2 "
    "(needs 25). Unit costs: P1 to C1 is 2, P1 to C2 is 4, P2 to C1 is 3, P2 to C2 is 1."
)
PROBLEM = {
    "sources": [{"id": "P1", "supply": 20}, {"id": "P2", "supply": 30}],
    "destinations": [{"id": "C1", "demand": 25}, {"id": "C2", "demand": 25}],
    "routes": [
        {"source": "P1", "destination": "C1", "cost": 2},
        {"source": "P1", "destination": "C2", "cost": 4},
        {"source": "P2", "destination": "C1", "cost": 3},
        {"source": "P2", "destination": "C2", "cost": 1},
    ],
}


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path) -> Iterator[None]:
    store = DatasetStore(tmp_path, max_file_bytes=100_000, max_files=5)
    app.dependency_overrides[get_store] = lambda: store
    yield
    app.dependency_overrides.clear()


def use_llm(llm: object) -> None:
    app.dependency_overrides[get_llm] = lambda: llm


def test_analyze() -> None:
    use_llm(
        FakeLLM(
            {
                "kind": "transportation",
                "summary": "Ship from two plants to two cities.",
                "requirements": ["minimize cost"],
                "questions": [],
            }
        )
    )
    body = client.post("/api/v1/agent/analyze", json={"text": TEXT}).json()
    assert body["analysis"]["kind"] == "transportation"
    assert len(body["trace"]["calls"]) == 1


def test_extract_from_text_returns_formulation() -> None:
    use_llm(FakeLLM(PROBLEM))
    body = client.post(
        "/api/v1/agent/extract", json={"text": TEXT, "kind": "transportation"}
    ).json()
    assert body["problem"]["kind"] == "transportation"
    assert body["ungrounded"] == []
    assert body["formulation"]["constraints"][0]["items"][0] == "Ship at most 20 out of P1"


def test_answers_count_as_text_for_grounding() -> None:
    problem = {**PROBLEM, "sources": [{"id": "P1", "supply": 20}, {"id": "P2", "supply": 35}]}
    use_llm(FakeLLM(problem))
    body = client.post(
        "/api/v1/agent/extract",
        json={
            "text": TEXT,
            "kind": "transportation",
            "answers": [{"question": "P2 supply this week?", "answer": "35 units"}],
        },
    ).json()
    assert body["ungrounded"] == []


def test_extract_from_data_uses_the_mapping() -> None:
    dataset_id = client.post("/api/v1/datasets/samples/sunray").json()["meta"]["id"]
    use_llm(
        FakeLLM(
            {
                "costs": {"layout": "matrix", "table": "costs.csv", "row_id_column": "silo"},
                "supply": {
                    "table": "silos.csv",
                    "id_column": "silo",
                    "value_column": "supply_tons",
                },
                "demand": {
                    "table": "mills.csv",
                    "id_column": "mill",
                    "value_column": "demand_tons",
                },
            }
        )
    )
    body = client.post(
        "/api/v1/agent/extract",
        json={"text": "Minimize cost.", "kind": "transportation", "dataset_id": dataset_id},
    ).json()
    assert body["mapping"]["costs"]["layout"] == "matrix"
    solved = client.post("/api/v1/solve", json=body["problem"]).json()
    assert solved["result"]["objective"] == 435


def test_llm_failure_is_a_502() -> None:
    class Down:
        model = "down"

        async def chat(self, messages: list[Message], schema: dict[str, object]) -> LLMReply:
            raise LLMError("Ollama error 404: model 'x' not found (run: ollama pull x)")

    use_llm(Down())
    response = client.post("/api/v1/agent/analyze", json={"text": TEXT})
    assert response.status_code == 502
    assert "ollama pull" in response.json()["detail"]


def test_formulation_endpoint() -> None:
    body = client.post("/api/v1/formulation", json={"kind": "transportation", **PROBLEM}).json()
    assert body["objective_latex"].startswith(r"\min")

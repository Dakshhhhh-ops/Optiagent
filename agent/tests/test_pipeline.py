import pytest

from optiagent_agent.grounding import numbers_in, ungrounded_values
from optiagent_agent.llm import LLMError, Trace, structured
from optiagent_agent.pipeline import (
    Analysis,
    Answer,
    analyze,
    extract_from_data,
    extract_from_text,
    with_answers,
)
from optiagent_agent.testing import FakeLLM
from optiagent_core.examples import sample_dataset_files
from optiagent_core.ingest import profile_table, read_file
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem

TEXT = (
    "Two plants, P1 (20 units) and P2 (30 units), supply cities C1 (needs 25) and C2 "
    "(needs 25). Unit costs: P1 to C1 is 2, P1 to C2 is 4, P2 to C1 is 3, P2 to C2 is 1."
)
GOOD = {
    "sources": [{"id": "P1", "supply": 20}, {"id": "P2", "supply": 30}],
    "destinations": [{"id": "C1", "demand": 25}, {"id": "C2", "demand": 25}],
    "routes": [
        {"source": "P1", "destination": "C1", "cost": 2},
        {"source": "P1", "destination": "C2", "cost": 4},
        {"source": "P2", "destination": "C1", "cost": 3},
        {"source": "P2", "destination": "C2", "cost": 1},
    ],
}


# --------------------------------------------------------------------------- structured()


async def test_structured_retries_with_the_errors() -> None:
    llm = FakeLLM("not json", {"kind": "assignment", "summary": "s", "requirements": []})
    trace = Trace()
    result = await structured(llm, step="t", system="sys", user="u", output=Analysis, trace=trace)
    assert result.kind == "assignment"
    assert [c.ok for c in trace.calls] == [False, True]
    retry_prompt = llm.seen[1][-1]["content"]
    assert retry_prompt.startswith("That JSON has problems")


async def test_structured_gives_up() -> None:
    llm = FakeLLM("{}", "{}", "{}")
    with pytest.raises(LLMError, match="no valid JSON after 3 attempts"):
        await structured(llm, step="t", system="s", user="u", output=Analysis, trace=Trace())


# --------------------------------------------------------------------------- grounding


def test_numbers_in_text() -> None:
    found = numbers_in("Ship 1,200 units at $3.50; each lab needs two TAs, not 3x.")
    assert {1200.0, 3.5, 2.0} <= found
    assert 3.0 not in found  # "3x" is not a standalone number


def test_ungrounded_values() -> None:
    problem = TransportationProblem.model_validate(
        {**GOOD, "routes": [*GOOD["routes"][:3], {"source": "P2", "destination": "C2", "cost": 7}]}
    )
    [bad] = ungrounded_values(problem, TEXT)
    assert bad.field == "cost P2 → C2"
    assert bad.value == 7


def test_default_capacity_and_requirement_need_no_mention() -> None:
    problem = AssignmentProblem.model_validate(
        {
            "agents": [{"id": "A"}],
            "tasks": [{"id": "T", "required": 1}],
            "pairings": [{"agent": "A", "task": "T", "value": 5}],
        }
    )
    assert ungrounded_values(problem, "A can do T for 5.") == []


# --------------------------------------------------------------------------- pipeline steps


async def test_analyze() -> None:
    llm = FakeLLM(
        {
            "kind": "transportation",
            "summary": "Ship from two plants to two cities.",
            "requirements": ["minimize cost", "meet each city's demand"],
            "questions": [],
        }
    )
    analysis, trace = await analyze(llm, TEXT)
    assert analysis.kind == "transportation"
    assert len(trace.calls) == 1


async def test_extract_retries_on_invented_number() -> None:
    invented = {
        **GOOD,
        "routes": [*GOOD["routes"][:3], {"source": "P2", "destination": "C2", "cost": 7}],
    }
    llm = FakeLLM(invented, GOOD)
    result = await extract_from_text(llm, TEXT, "transportation")

    assert result.ungrounded == []
    assert len(result.trace.calls) == 2
    assert "cost P2 → C2 = 7 does not appear" in llm.seen[1][-1]["content"]
    assert result.problem is not None
    assert solve_problem(result.problem).result.objective == pytest.approx(80)


async def test_extract_reports_ungrounded_after_last_attempt() -> None:
    invented = {**GOOD, "sources": [{"id": "P1", "supply": 99}, {"id": "P2", "supply": 30}]}
    result = await extract_from_text(FakeLLM(invented, invented, invented), TEXT, "transportation")
    assert [u.field for u in result.ungrounded] == ["supply of P1"]


async def test_answers_are_part_of_the_text() -> None:
    text = with_answers("P1 supplies C1.", [Answer(question="Cost?", answer="4 per unit")])
    assert "Q: Cost?\nA: 4 per unit" in text
    assert 4.0 in numbers_in(text)


async def test_extract_from_data_fixes_a_wrong_table() -> None:
    files = sample_dataset_files("sunray")
    tables = [t for name, data in files for t in read_file(name, data)]
    profiles = [profile_table(t) for t in tables]
    wrong = {
        "costs": {"layout": "matrix", "table": "cost.csv", "row_id_column": "silo"},
        "supply": {"table": "silos.csv", "id_column": "silo", "value_column": "supply_tons"},
        "demand": {"table": "mills.csv", "id_column": "mill", "value_column": "demand_tons"},
    }
    right = {**wrong, "costs": {**wrong["costs"], "table": "costs.csv"}}
    llm = FakeLLM(wrong, right)

    result = await extract_from_data(
        llm, "Minimize shipping cost.", "transportation", tables, profiles
    )
    assert "no table named 'cost.csv'" in llm.seen[1][-1]["content"]
    assert result.problem is not None
    assert solve_problem(result.problem).result.objective == pytest.approx(435)

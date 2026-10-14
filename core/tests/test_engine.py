import itertools
import random

import pytest
from pydantic import ValidationError

from optiagent_core.builders import build_model
from optiagent_core.checks import verify_solution
from optiagent_core.pipeline import AssignmentSolution, TransportationSolution, solve_problem
from optiagent_core.schema import (
    Agent,
    AssignmentProblem,
    Destination,
    Pairing,
    Route,
    Source,
    Task,
    TransportationProblem,
)
from optiagent_core.solver import solve


def small_transport() -> TransportationProblem:
    return TransportationProblem(
        sources=[Source(id="S1", supply=20), Source(id="S2", supply=30)],
        destinations=[Destination(id="D1", demand=25), Destination(id="D2", demand=25)],
        routes=[
            Route(source="S1", destination="D1", cost=2),
            Route(source="S1", destination="D2", cost=4),
            Route(source="S2", destination="D1", cost=3),
            Route(source="S2", destination="D2", cost=1),
        ],
    )


# --------------------------------------------------------------------------- schema


def test_rejects_unknown_route_endpoint() -> None:
    with pytest.raises(ValidationError, match="unknown destination"):
        TransportationProblem(
            sources=[Source(id="S1", supply=1)],
            destinations=[Destination(id="D1", demand=1)],
            routes=[Route(source="S1", destination="Nowhere", cost=1)],
        )


def test_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate source ids: S1"):
        TransportationProblem(
            sources=[Source(id="S1", supply=1), Source(id="S1", supply=2)],
            destinations=[Destination(id="D1", demand=1)],
            routes=[Route(source="S1", destination="D1", cost=1)],
        )


def test_rejects_negative_supply() -> None:
    with pytest.raises(ValidationError):
        Source(id="S1", supply=-5)


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Source.model_validate({"id": "S1", "supply": 1, "suply": 2})


# --------------------------------------------------------------------------- builder


def test_builder_structure() -> None:
    model = build_model(small_transport())
    assert len(model.variables) == 4
    assert [c.name for c in model.constraints] == [
        "supply[S1]",
        "supply[S2]",
        "demand[D1]",
        "demand[D2]",
    ]
    supply = model.constraints[0]
    assert supply.sense == "<=" and supply.rhs == 20
    assert set(supply.terms) == {"x[S1,D1]", "x[S1,D2]"}
    assert model.constraints[2].sense == "=="


def test_at_least_demand_uses_ge() -> None:
    problem = small_transport().model_copy(update={"demand_constraint": "at_least"})
    assert build_model(problem).constraints[2].sense == ">="


# --------------------------------------------------------------------------- solution checks


def test_checks_catch_a_violated_constraint() -> None:
    model = build_model(small_transport())
    result = solve(model)
    tampered = result.model_copy(update={"values": {**result.values, "x[S2,D2]": 0.0}})
    report = verify_solution(model, tampered)
    failed = {c.name for c in report.checks if not c.passed}
    assert "constraints_satisfied" in failed
    assert not report.passed


def test_checks_catch_a_wrong_objective() -> None:
    model = build_model(small_transport())
    result = solve(model)
    tampered = result.model_copy(update={"objective": result.objective + 1})  # type: ignore[operator]
    failed = {c.name for c in verify_solution(model, tampered).checks if not c.passed}
    assert failed == {"objective_recomputed"}


def test_checks_catch_a_bound_violation() -> None:
    model = build_model(small_transport())
    result = solve(model)
    tampered = result.model_copy(update={"values": {**result.values, "x[S1,D2]": -1.0}})
    failed = {c.name for c in verify_solution(model, tampered).checks if not c.passed}
    assert "variable_bounds" in failed


def test_checks_catch_fractional_assignment() -> None:
    problem = AssignmentProblem(
        agents=[Agent(id="A"), Agent(id="B")],
        tasks=[Task(id="T")],
        pairings=[Pairing(agent="A", task="T", value=1), Pairing(agent="B", task="T", value=1)],
    )
    model = build_model(problem)
    result = solve(model)
    tampered = result.model_copy(update={"values": {"y[A,T]": 0.5, "y[B,T]": 0.5}})
    failed = {c.name for c in verify_solution(model, tampered).checks if not c.passed}
    assert failed == {"integrality"}


# --------------------------------------------------------------------------- interpretation


def test_transportation_solution_is_interpreted() -> None:
    report = solve_problem(small_transport())
    solution = report.solution
    assert isinstance(solution, TransportationSolution)
    flows = {(s.source, s.destination): s.quantity for s in solution.shipments}
    assert flows == pytest.approx({("S1", "D1"): 20, ("S2", "D1"): 5, ("S2", "D2"): 25})
    assert sum(s.cost for s in solution.shipments) == pytest.approx(80)
    assert all(u.unused == pytest.approx(0) for u in solution.sources)


def test_lp_returns_duals_and_reduced_costs() -> None:
    report = solve_problem(small_transport())
    assert set(report.result.duals) == {c.name for c in report.model.constraints}
    assert set(report.result.reduced_costs) == {v.name for v in report.model.variables}


# ------------------------------------------------------------------ brute-force cross-check


@pytest.mark.parametrize("seed", range(20))
def test_assignment_matches_brute_force(seed: int) -> None:
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    sense = rng.choice(["minimize", "maximize"])
    cost = [[rng.randint(1, 50) for _ in range(n)] for _ in range(n)]
    problem = AssignmentProblem(
        sense=sense,
        agents=[Agent(id=f"a{i}") for i in range(n)],
        tasks=[Task(id=f"t{j}") for j in range(n)],
        pairings=[
            Pairing(agent=f"a{i}", task=f"t{j}", value=cost[i][j])
            for i in range(n)
            for j in range(n)
        ],
    )

    totals = [sum(cost[i][p[i]] for i in range(n)) for p in itertools.permutations(range(n))]
    best = min(totals) if sense == "minimize" else max(totals)

    report = solve_problem(problem)
    assert report.verified
    assert report.result.objective == pytest.approx(best)
    assert isinstance(report.solution, AssignmentSolution)
    assert len(report.solution.assignments) == n

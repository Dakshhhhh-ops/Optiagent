"""Regression and property tests for input validation, plan verification and analysis wording."""

import itertools
import math
import random

import pytest
from pydantic import ValidationError

from optiagent_core import pipeline
from optiagent_core.builders import assign_var, build_model, flow_var
from optiagent_core.checks import verify_solution
from optiagent_core.ingest.tables import parse_number
from optiagent_core.pipeline import solve_problem
from optiagent_core.plancheck import check_plan
from optiagent_core.schema import AssignmentProblem, TransportationProblem
from optiagent_core.solver import SolveResult, SolveStatus, solve


def _transport(**kw: object) -> TransportationProblem:
    base: dict[str, object] = {
        "sources": [{"id": "A", "supply": 10}, {"id": "B", "supply": 10}],
        "destinations": [{"id": "X", "demand": 8}, {"id": "Y", "demand": 7}],
        "routes": [
            {"source": "A", "destination": "X", "cost": 2},
            {"source": "A", "destination": "Y", "cost": 5},
            {"source": "B", "destination": "X", "cost": 4},
            {"source": "B", "destination": "Y", "cost": 3},
        ],
    }
    return TransportationProblem.model_validate({**base, **kw})


# --------------------------------------------------------------------------- input validation


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_costs_are_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        _transport(routes=[{"source": "A", "destination": "X", "cost": bad}])


def test_non_finite_quantities_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _transport(sources=[{"id": "A", "supply": math.inf}, {"id": "B", "supply": 1}])
    with pytest.raises(ValidationError):
        AssignmentProblem.model_validate(
            {
                "agents": [{"id": "a"}],
                "tasks": [{"id": "t"}],
                "pairings": [{"agent": "a", "task": "t", "value": math.nan}],
            }
        )


def test_json_nan_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TransportationProblem.model_validate_json(
            '{"sources":[{"id":"A","supply":1}],"destinations":[{"id":"X","demand":1}],'
            '"routes":[{"source":"A","destination":"X","cost":NaN}]}'
        )


@pytest.mark.parametrize("cell", ["inf", "Infinity", "1e999", "-1e999", math.nan, math.inf])
def test_file_cells_never_parse_to_non_finite(cell: str | float) -> None:
    assert parse_number(cell) is None


def test_ordinary_file_cells_still_parse() -> None:
    assert parse_number("$1,200.50") == 1200.5
    assert parse_number(3) == 3.0


# --------------------------------------------------------------------------- plan verification


def test_plan_checks_catch_a_builder_bug_that_model_checks_miss() -> None:
    """Drop a demand constraint from the built model, as a buggy builder would. The solver's
    answer satisfies the wrong model, so Layer 1 passes; the problem-level checks fail."""
    problem = _transport()
    model = build_model(problem)
    model.constraints = [c for c in model.constraints if c.name != "demand[Y]"]
    result = solve(model)
    assert verify_solution(model, result).passed
    failed = {c.name for c in check_plan(problem, result.values, result.objective) if not c.passed}
    assert "plan_demand_met" in failed


def test_plan_checks_catch_a_flipped_supply_sign() -> None:
    problem = _transport(sources=[{"id": "A", "supply": 3}, {"id": "B", "supply": 20}])
    model = build_model(problem)
    for c in model.constraints:
        if c.name == "supply[A]":
            c.sense = ">="  # a sign bug in the builder
    result = solve(model)
    assert result.status == SolveStatus.OPTIMAL
    failed = {c.name for c in check_plan(problem, result.values, result.objective) if not c.passed}
    assert "plan_supply_respected" in failed


def test_plan_checks_reject_unlisted_pairs_and_fractions() -> None:
    problem = AssignmentProblem.model_validate(
        {
            "agents": [{"id": "a"}, {"id": "b"}],
            "tasks": [{"id": "t"}],
            "pairings": [{"agent": "a", "task": "t", "value": 3}],
        }
    )
    values = {assign_var("a", "t"): 0.5, assign_var("b", "t"): 0.5}
    failed = {c.name for c in check_plan(problem, values, 1.5) if not c.passed}
    assert {"plan_covers_allowed_pairs_only", "plan_whole_assignments"} <= failed


def test_plan_objective_is_recomputed_from_the_data() -> None:
    problem = _transport()
    report = solve_problem(problem)
    values = report.result.values
    checks = {c.name: c for c in check_plan(problem, values, (report.result.objective or 0) + 1)}
    assert not checks["plan_objective_from_data"].passed


def test_no_business_plan_when_verification_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    real_solve = pipeline.solve

    def lying_solver(model: object) -> SolveResult:
        result = real_solve(model)  # type: ignore[arg-type]
        result.objective = (result.objective or 0) - 10  # claims a better optimum
        return result

    monkeypatch.setattr(pipeline, "solve", lying_solver)
    report = solve_problem(_transport())
    assert not report.verified
    assert report.outcome == "verification_failed"
    assert report.solution is None
    assert report.result.values  # raw values stay available for inspection


def test_outcomes_are_distinct() -> None:
    assert solve_problem(_transport()).outcome == "verified_optimal"
    short = _transport(destinations=[{"id": "X", "demand": 30}, {"id": "Y", "demand": 7}])
    report = solve_problem(short, analyze=True)
    assert report.outcome == "infeasible" and report.solution is None
    assert report.diagnosis is not None and "every unit of shortfall counts the same" in (
        report.diagnosis.method
    )
    assert report.diagnosis.relaxed == ["demand[X]", "demand[Y]"]


def test_every_verified_report_carries_problem_level_checks() -> None:
    scopes = {c.scope for c in solve_problem(_transport()).verification.checks}
    assert scopes == {"status", "model", "problem"}


# --------------------------------------------------------------------------- property tests


def _random_assignment(rng: random.Random) -> AssignmentProblem:
    n = rng.randint(2, 5)
    agents = [f"a{i}" for i in range(n)]
    tasks = [f"t{j}" for j in range(rng.randint(1, n))]
    pairings = [
        {"agent": a, "task": t, "value": rng.randint(1, 20)}
        for a in agents
        for t in tasks
        if rng.random() < 0.8
    ]
    return AssignmentProblem.model_validate(
        {
            "sense": rng.choice(["minimize", "maximize"]),
            "agents": [{"id": a} for a in agents],
            "tasks": [{"id": t} for t in tasks],
            "pairings": pairings or [{"agent": agents[0], "task": tasks[0], "value": 1}],
        }
    )


def _brute_force(problem: AssignmentProblem) -> float | None:
    """Independent answer key: try every injective task -> agent map."""
    values = {(p.agent, p.task): p.value for p in problem.pairings}
    agents = [a.id for a in problem.agents]
    tasks = [t.id for t in problem.tasks]
    best: float | None = None
    for chosen in itertools.permutations(agents, len(tasks)):
        if all((a, t) in values for a, t in zip(chosen, tasks, strict=True)):
            total = sum(values[(a, t)] for a, t in zip(chosen, tasks, strict=True))
            if best is None or (total < best if problem.sense == "minimize" else total > best):
                best = total
    return best


@pytest.mark.parametrize("seed", range(40))
def test_assignment_optimum_matches_brute_force(seed: int) -> None:
    problem = _random_assignment(random.Random(seed))
    report = solve_problem(problem)
    expected = _brute_force(problem)
    if expected is None:
        assert report.outcome == "infeasible"
    else:
        assert report.outcome == "verified_optimal"
        assert report.result.objective == pytest.approx(expected)


@pytest.mark.parametrize("seed", range(40))
def test_random_transportation_plans_verify_against_the_data(seed: int) -> None:
    rng = random.Random(1000 + seed)
    sources = [{"id": f"S{i}", "supply": rng.randint(0, 40)} for i in range(rng.randint(1, 4))]
    dests = [{"id": f"D{j}", "demand": rng.randint(0, 30)} for j in range(rng.randint(1, 4))]
    routes = [
        {
            "source": s["id"],
            "destination": d["id"],
            "cost": rng.randint(-3, 15),
            "capacity": rng.choice([None, rng.randint(0, 25)]),
        }
        for s in sources
        for d in dests
        if rng.random() < 0.85
    ] or [{"source": "S0", "destination": "D0", "cost": 1}]
    problem = TransportationProblem.model_validate(
        {
            "sense": rng.choice(["minimize", "maximize"]),
            "demand_constraint": rng.choice(["equal", "at_least"]),
            "sources": sources,
            "destinations": dests,
            "routes": routes,
        }
    )
    report = solve_problem(problem)
    assert report.outcome in {"verified_optimal", "infeasible"}
    if report.outcome == "verified_optimal":
        values = report.result.values
        total = sum(r.cost * values[flow_var(r.source, r.destination)] for r in problem.routes)
        assert report.result.objective == pytest.approx(total, abs=1e-6)
        assert all(c.passed for c in report.verification.checks)


# --------------------------------------------------------------------------- analysis wording


def test_zero_requirement_cannot_be_decreased() -> None:
    problem = TransportationProblem.model_validate(
        {
            "sources": [{"id": "A", "supply": 10}, {"id": "B", "supply": 0}],
            "destinations": [{"id": "X", "demand": 10}, {"id": "Y", "demand": 0}],
            "routes": [
                {"source": "A", "destination": "X", "cost": 2},
                {"source": "B", "destination": "Y", "cost": 1},
            ],
        }
    )
    report = solve_problem(problem, analyze=True)
    assert report.sensitivity is not None
    y = next(c for c in report.sensitivity.constraints if c.name == "demand[Y]")
    assert y.effect_if_decreased == "not_applicable"
    text = " ".join(i.text for i in report.insights if i.source == "demand[Y]")
    assert "not possible" in text and "one less would make the plan infeasible" not in text


def test_tied_routes_are_reported_as_alternative_optima() -> None:
    problem = TransportationProblem.model_validate(
        {
            "sources": [{"id": "A", "supply": 10}, {"id": "B", "supply": 10}],
            "destinations": [{"id": "X", "demand": 10}],
            "routes": [
                {"source": "A", "destination": "X", "cost": 2},
                {"source": "B", "destination": "X", "cost": 2},
            ],
        }
    )
    report = solve_problem(problem, analyze=True)
    assert report.sensitivity is not None and report.sensitivity.alternative_optima
    assert any(i.kind == "alternative_optimum" for i in report.insights)


def test_unique_optimum_reports_no_alternative() -> None:
    report = solve_problem(_transport(), analyze=True)
    assert report.sensitivity is not None and not report.sensitivity.alternative_optima


def test_route_limit_effect_is_an_exact_resolve() -> None:
    # A -> X is cheap but limited to 5; X needs 8, so 3 come from B at 4 instead of 2.
    problem = _transport(
        routes=[
            {"source": "A", "destination": "X", "cost": 2, "capacity": 5},
            {"source": "A", "destination": "Y", "cost": 5},
            {"source": "B", "destination": "X", "cost": 4},
            {"source": "B", "destination": "Y", "cost": 3},
        ]
    )
    report = solve_problem(problem, analyze=True)
    assert report.sensitivity is not None
    v = next(v for v in report.sensitivity.variables if v.name == flow_var("A", "X"))
    assert v.status == "at_upper"
    assert v.change_if_limit_raised == pytest.approx(-2)

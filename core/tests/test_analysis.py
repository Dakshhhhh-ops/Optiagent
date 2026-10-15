import random

import pytest

from optiagent_core.analysis import analyze_sensitivity
from optiagent_core.builders import build_model
from optiagent_core.diagnose import diagnose
from optiagent_core.examples import list_examples
from optiagent_core.explain import explain
from optiagent_core.model import LinearModel, Origin, Variable
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import (
    AssignmentProblem,
    Destination,
    Route,
    Source,
    TransportationProblem,
)

EXAMPLES = {e.id: e.problem for e in list_examples()}


def test_hand_computed_marginals_on_t3() -> None:
    """t3: S1=50, S2=40, D1=D2=30; S1->D1 costs 5 (cap 20), S1->D2 8, S2->D1 6, S2->D2 4.

    Optimum 280: S1->D1 20, S2->D1 10, S2->D2 30. By hand:
      one more unit at D1: S2->D1 +1 (+6), S2->D2 -1 (-4), S1->D2 +1 (+8)  -> +10
      one less unit at D1: S2->D1 -1                                        -> -6
      one more unit at D2: S1->D2 +1                                        -> +8
      one less unit at S2: S2->D2 -1 (-4), S1->D2 +1 (+8)                   -> +4
      raising the S1->D1 cap by 1: S1->D1 +1 (+5), S2->D1 -1 (-6)           -> -1
    """
    s = analyze_sensitivity(build_model(EXAMPLES["t3_excess_supply_with_route_cap"]))
    c = {x.name: x for x in s.constraints}
    assert s.objective == pytest.approx(280)
    assert c["demand[D1]"].change_if_increased == pytest.approx(10)
    assert c["demand[D1]"].change_if_decreased == pytest.approx(-6)
    assert c["demand[D2]"].change_if_increased == pytest.approx(8)
    assert c["supply[S2]"].change_if_decreased == pytest.approx(4)
    assert not c["supply[S1]"].binding and c["supply[S1]"].slack == pytest.approx(30)

    v = {x.name: x for x in s.variables}
    assert v["x[S1,D1]"].status == "at_upper"
    assert v["x[S1,D1]"].reduced_cost == pytest.approx(-1)
    assert s.degenerate  # the duals above are one-sided


def test_raising_the_cap_matches_reduced_cost() -> None:
    p = EXAMPLES["t3_excess_supply_with_route_cap"]
    assert isinstance(p, TransportationProblem)
    routes = [r.model_copy(update={"capacity": 21}) if r.capacity else r for r in p.routes]
    raised = solve_problem(p.model_copy(update={"routes": routes})).result.objective
    assert raised is not None
    assert raised - 280 == pytest.approx(-1)


@pytest.mark.parametrize("example", sorted(k for k in EXAMPLES if not k.startswith("x")))
def test_highs_agrees_with_glop(example: str) -> None:
    problem = EXAMPLES[example]
    s = analyze_sensitivity(build_model(problem))
    assert s.available
    assert s.objective == pytest.approx(solve_problem(problem).result.objective)


def random_transport(seed: int) -> TransportationProblem:
    rng = random.Random(seed)
    sources = [Source(id=f"S{i}", supply=rng.randint(10, 60)) for i in range(rng.randint(2, 4))]
    total = sum(s.supply for s in sources)
    dests = [Destination(id=f"D{j}", demand=rng.randint(5, 30)) for j in range(rng.randint(2, 4))]
    while sum(d.demand for d in dests) > total:
        dests = [d.model_copy(update={"demand": max(1, d.demand // 2)}) for d in dests]
    routes = [
        Route(source=s.id, destination=d.id, cost=rng.randint(1, 20))
        for s in sources
        for d in dests
    ]
    return TransportationProblem(sources=sources, destinations=dests, routes=routes)


@pytest.mark.parametrize("seed", range(30))
def test_duals_equal_one_unit_resolve_inside_their_range(seed: int) -> None:
    problem = random_transport(seed)
    s = analyze_sensitivity(build_model(problem))
    assert s.objective == pytest.approx(solve_problem(problem).result.objective)
    for c in s.constraints:
        if not c.binding:
            assert c.shadow_price == pytest.approx(0, abs=1e-9)
            continue
        if (
            c.rhs_to is not None
            and c.rhs + 1 <= c.rhs_to + 1e-9
            and c.change_if_increased is not None
        ):
            assert c.change_if_increased == pytest.approx(c.shadow_price), c.name
        if (
            c.rhs_from is not None
            and c.rhs - 1 >= c.rhs_from - 1e-9
            and c.change_if_decreased is not None
        ):
            assert c.change_if_decreased == pytest.approx(-c.shadow_price), c.name


def test_mip_has_no_duals() -> None:
    model = LinearModel(
        name="m",
        sense="minimize",
        variables=[Variable(name="x", integer=True, ub=3, objective=1, origin=Origin(kind="x"))],
    )
    assert not analyze_sensitivity(model).available


def test_diagnose_transportation_shortfall() -> None:
    d = diagnose(build_model(EXAMPLES["x1_infeasible_short_supply"]))
    assert d.relaxed_feasible
    assert d.total_shortfall == pytest.approx(10)
    assert "At least 10 unit(s) cannot be covered" in d.explanation


def test_diagnose_assignment_shortfall() -> None:
    problem = AssignmentProblem.model_validate(
        {
            "agents": [{"id": "A"}, {"id": "B"}],
            "tasks": [{"id": "T", "required": 2}, {"id": "U"}],
            "pairings": [
                {"agent": "A", "task": "T", "value": 1},
                {"agent": "B", "task": "U", "value": 1},
            ],
        }
    )
    assert solve_problem(problem).result.status == "infeasible"
    d = diagnose(build_model(problem))
    assert d.total_shortfall == pytest.approx(1)
    assert d.shortfalls[0].id == "T"
    assert "position(s)" in d.explanation


def test_insights_use_exact_one_unit_effects() -> None:
    p = EXAMPLES["t3_excess_supply_with_route_cap"]
    insights = explain(analyze_sensitivity(build_model(p)), minimize=True, transport=True)
    texts = [i.text for i in insights]
    assert texts[0].startswith(
        "One more unit of demand at D1 would worsen the total cost by 10; one less would improve "
        "the total cost by 6."
    )
    assert any("S1 → D2 is not used" in t and "below 4" in t for t in texts)
    assert any(
        "Raising the limit by one unit would improve the total cost by 1." in t for t in texts
    )


def test_highs_and_ortools_never_share_a_process() -> None:
    """Both ship HiGHS; on Linux they cannot be loaded into one process (see highs_worker)."""
    import subprocess
    import sys

    analyze_sensitivity(build_model(EXAMPLES["t1_two_by_two"]))
    assert "highspy" not in sys.modules

    probe = (
        "import sys, optiagent_core.highs_worker as w; "
        "w.run_highs(open(sys.argv[1]).read()); "
        "assert not any(m.startswith('ortools') for m in sys.modules), 'ortools loaded'"
    )
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write(build_model(EXAMPLES["t1_two_by_two"]).model_dump_json())
    subprocess.run([sys.executable, "-c", probe, f.name], check=True)


def test_unused_route_that_would_stay_unused_even_if_free() -> None:
    p = EXAMPLES["t2_sunray"]
    insights = explain(analyze_sensitivity(build_model(p)), minimize=True, transport=True)
    texts = [i.text for i in insights if i.kind == "unused_option"]
    assert not any("below -" in t for t in texts)
    assert any("would stay unused even if it cost nothing" in t for t in texts)

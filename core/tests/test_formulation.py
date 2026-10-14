from optiagent_core.examples import list_examples
from optiagent_core.formulation import describe_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem


def example(example_id: str) -> TransportationProblem | AssignmentProblem:
    return next(e.problem for e in list_examples() if e.id == example_id)


def test_transportation_formulation() -> None:
    f = describe_problem(example("t2_sunray"))
    assert f.objective_latex.startswith(r"\min")
    assert "12 allowed routes" in f.objective_english
    supply, demand = f.constraints
    assert supply.items[0] == "Ship at most 15 out of Silo1"
    assert demand.items[-1] == "Deliver exactly 15 to Mill4"
    assert "=" in demand.latex
    assert [s.members for s in f.sets[:2]] == [
        ["Silo1", "Silo2", "Silo3"],
        ["Mill1", "Mill2", "Mill3", "Mill4"],
    ]
    assert f.notes == []


def test_transportation_notes_and_route_caps() -> None:
    f = describe_problem(example("t3_excess_supply_with_route_cap"))
    assert any("30 units can stay unused" in n for n in f.notes)
    assert f.constraints[-1].name == "Route capacity"
    assert f.constraints[-1].items == ["Ship at most 20 from S1 to D1"]


def test_infeasible_supply_is_called_out() -> None:
    f = describe_problem(example("x1_infeasible_short_supply"))
    assert any("will be infeasible" in n for n in f.notes)


def test_assignment_formulation() -> None:
    f = describe_problem(example("a2_ta_labs_preferences"))
    assert f.objective_latex.startswith(r"\max")
    assert "Maximize total score" in f.objective_english
    assert any("1 agent–task pair(s) are not allowed" in n for n in f.notes)
    assert "L1 gets exactly 2 agent(s)" in f.constraints[1].items

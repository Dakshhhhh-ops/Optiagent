import pytest

from optiagent_agent.review import RequirementCheck, Review
from optiagent_agent.traceability import trace, unsupported_statements
from optiagent_core.ingest import KeyValue, LongLayout, TransportationMapping
from optiagent_core.schema import AssignmentProblem, TransportationProblem

TEXT = (
    "Plant A has 30 units and Plant B has 20 units. Store X needs 25 units and Store Y needs "
    "25 units. Shipping from Plant A to Store X costs 4, Plant A to Store Y costs 6, Plant B to "
    "Store X costs 5 and Plant B to Store Y costs 3. Minimize the total shipping cost."
)


def _problem(**changes: object) -> TransportationProblem:
    data: dict[str, object] = {
        "sources": [{"id": "Plant A", "supply": 30}, {"id": "Plant B", "supply": 20}],
        "destinations": [{"id": "Store X", "demand": 25}, {"id": "Store Y", "demand": 25}],
        "routes": [
            {"source": "Plant A", "destination": "Store X", "cost": 4},
            {"source": "Plant A", "destination": "Store Y", "cost": 6},
            {"source": "Plant B", "destination": "Store X", "cost": 5},
            {"source": "Plant B", "destination": "Store Y", "cost": 3},
        ],
    }
    return TransportationProblem.model_validate({**data, **changes})


def _provenance(report: object, parameter: str) -> object:
    return next(p for p in report.provenance if p.parameter == parameter)  # type: ignore[attr-defined]


def test_correct_model_is_checked_with_evidence() -> None:
    report = trace(_problem(), TEXT)
    assert report.status == "checked"
    cost = _provenance(report, "cost Plant A → Store X")
    assert cost.status == "verified" and "costs 4" in cost.evidence  # type: ignore[attr-defined]
    objective = next(r for r in report.requirements if r.model_element == "objective sense")
    assert objective.status == "verified"


def test_altered_value_is_unresolved_with_the_stated_value() -> None:
    routes = [r.model_dump() for r in _problem().routes]
    routes[0]["cost"] = 7
    report = trace(_problem(routes=routes), TEXT)
    cost = _provenance(report, "cost Plant A → Store X")
    assert cost.status == "unresolved" and "the text says 4" in cost.evidence  # type: ignore[attr-defined]
    assert report.status == "needs_review"


def test_invented_number_is_unresolved() -> None:
    routes = [r.model_dump() for r in _problem().routes]
    routes[1]["capacity"] = 12
    report = trace(_problem(routes=routes), TEXT)
    limit = _provenance(report, "limit Plant A → Store Y")
    assert limit.status == "unresolved" and limit.source == "unknown"  # type: ignore[attr-defined]
    assert any("route limit the text does not state" in r.note for r in report.requirements)


def test_wrong_objective_direction_is_unresolved() -> None:
    report = trace(_problem(sense="maximize"), TEXT)
    objective = next(r for r in report.requirements if r.model_element == "objective sense")
    assert objective.status == "unresolved"


def test_contradictory_values_are_unresolved() -> None:
    text = TEXT + " Correction: Plant A to Store X costs 9."
    cost = _provenance(trace(_problem(), text), "cost Plant A → Store X")
    assert cost.status == "unresolved" and "several values" in cost.evidence  # type: ignore[attr-defined]


def test_unlinked_number_is_only_represented() -> None:
    # The value 3 appears in the text (as B -> Y), but nothing ties it to a supply.
    text = TEXT.replace("Plant B has 20 units", "Plant B has plenty")
    report = trace(
        _problem(sources=[{"id": "Plant A", "supply": 30}, {"id": "Plant B", "supply": 3}]), text
    )
    supply = _provenance(report, "supply of Plant B")
    assert supply.status == "represented"


@pytest.mark.parametrize(
    "text",
    [
        "Opening a warehouse has a fixed cost of 500.",
        "Plan production for the next 4 weeks with inventory carried over.",
        "The total cost must not exceed our budget of 10,000.",
        "Each store must be served by a single supplier (single sourcing).",
        "Goods ship in full truckloads of 20 units.",
        "Everything goes via the hub in Nagpur before reaching stores.",
        "Ravi and Meena must work together.",
        "Balance the workload evenly across the team.",
    ],
)
def test_unsupported_semantics_are_flagged(text: str) -> None:
    rows = unsupported_statements(text)
    assert rows and rows[0].status == "unsupported"


def test_ordinary_text_has_no_unsupported_rows() -> None:
    assert unsupported_statements(TEXT) == []


def test_percentages_need_confirmation() -> None:
    rows = unsupported_statements("Routes from Plant A get a 10% discount.")
    assert [r.status for r in rows] == ["unresolved"]


def test_ai_review_cannot_verify_anything() -> None:
    review = Review(
        checks=[
            RequirementCheck(requirement="r1", status="covered", where="Objective"),
            RequirementCheck(requirement="r2", status="missing"),
            RequirementCheck(requirement="r3", status="not_applicable"),
        ]
    )
    report = trace(_problem(), TEXT, requirements=["r1", "r2", "r3", "r4"], review=review)
    ai = {r.requirement: r for r in report.requirements if r.requirement.startswith("r")}
    assert ai["r1"].status == "represented" and ai["r1"].method == "ai_review"
    assert ai["r2"].status == "unresolved"
    assert "r3" not in ai
    assert ai["r4"].status == "unresolved" and ai["r4"].method == "none"


def test_file_values_trace_to_their_columns() -> None:
    mapping = TransportationMapping(
        costs=LongLayout(table="routes", from_column="from", to_column="to", value_column="cost"),
        supply=KeyValue(table="plants", id_column="plant", value_column="supply"),
        demand=KeyValue(table="stores", id_column="store", value_column="demand"),
    )
    report = trace(_problem(), mapping=mapping)
    cost = _provenance(report, "cost Plant A → Store X")
    assert cost.source == "file" and "'routes'" in cost.evidence and "'cost'" in cost.evidence  # type: ignore[attr-defined]


def test_assignment_defaults_are_marked() -> None:
    problem = AssignmentProblem.model_validate(
        {
            "agents": [{"id": "Ravi"}, {"id": "Meena"}],
            "tasks": [{"id": "L1"}],
            "pairings": [
                {"agent": "Ravi", "task": "L1", "value": 8},
                {"agent": "Meena", "task": "L1", "value": 5},
            ],
        }
    )
    text = "Ravi: L1 8. Meena: L1 5. Each lab needs exactly one TA. Minimize the total cost."
    report = trace(problem, text)
    need = _provenance(report, "agents needed for L1")
    assert need.source == "default" and need.status == "verified"  # type: ignore[attr-defined]
    cap = _provenance(report, "capacity of Ravi")
    assert cap.status == "represented"  # nothing in the text says one task per TA

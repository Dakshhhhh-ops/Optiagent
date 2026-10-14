from optiagent_agent.audit import audit
from optiagent_agent.textfacts import extract_facts
from optiagent_core.schema import AssignmentProblem, TransportationProblem

TA_TEXT = (
    "Four TAs rank lab sections from 1 to 10. Ravi: L1 8, L2 2, L3 8. Omar: L1 8, L2 10, L3 4. "
    "Lena: L1 5, L2 8, L3 9. Meera: L1 4, L2 7, L3 5. L2 needs two TAs; L1 and L3 need one each. "
    "Each TA takes at most one section. Maximize the total preference score."
)
SCORES = {"Ravi": [8, 2, 8], "Omar": [8, 10, 4], "Lena": [5, 8, 9], "Meera": [4, 7, 5]}
TA = AssignmentProblem.model_validate(
    {
        "sense": "maximize",
        "agents": [{"id": a} for a in SCORES],
        "tasks": [{"id": "L1"}, {"id": "L2", "required": 2}, {"id": "L3"}],
        "pairings": [
            {"agent": a, "task": t, "value": v}
            for a, vs in SCORES.items()
            for t, v in zip(["L1", "L2", "L3"], vs, strict=True)
        ],
    }
)

SHIP_TEXT = (
    "The factory in Plant C can send up to 40 tons, shipping to Austin at $3 per ton and Seattle "
    "at $8 per ton. The factory in Plant B can send up to 30 tons, shipping to Austin at $11 per "
    "ton, Seattle at $18 per ton and Denver at $19 per ton. Austin requires 20 tons, Seattle 20 "
    "tons and Denver 30 tons. Plant C cannot ship to Denver. At most 15 tons can go from Plant B "
    "to Austin. Find the shipping plan with the lowest total cost."
)
SHIP = TransportationProblem.model_validate(
    {
        "sources": [{"id": "Plant C", "supply": 40}, {"id": "Plant B", "supply": 30}],
        "destinations": [
            {"id": "Austin", "demand": 20},
            {"id": "Seattle", "demand": 20},
            {"id": "Denver", "demand": 30},
        ],
        "routes": [
            {"source": "Plant C", "destination": "Austin", "cost": 3},
            {"source": "Plant C", "destination": "Seattle", "cost": 8},
            {"source": "Plant B", "destination": "Austin", "cost": 11, "capacity": 15},
            {"source": "Plant B", "destination": "Seattle", "cost": 18},
            {"source": "Plant B", "destination": "Denver", "cost": 19},
        ],
    }
)


def messages(report) -> list[str]:  # type: ignore[no-untyped-def]
    return [f.message for f in report.findings if f.severity != "info"]


def test_correct_models_pass_cleanly() -> None:
    assert messages(audit(TA, TA_TEXT)) == []
    assert messages(audit(SHIP, SHIP_TEXT)) == []


def test_facts_from_narrative_text() -> None:
    facts = extract_facts(SHIP_TEXT, SHIP)
    pairs = {(p.frm, p.to): p.value for p in facts.pairs}
    assert pairs[("Plant C", "Austin")] == 3
    assert pairs[("Plant B", "Denver")] == 19
    assert pairs[("Plant C", "Denver")] is None  # "cannot ship"
    assert [(f.frm, f.to, f.value) for f in facts.limits] == [("Plant B", "Austin", 15)]
    assert {(e.id, e.value) for e in facts.entities} >= {("Plant C", 40), ("Austin", 20)}


def test_dropped_pair_is_caught() -> None:
    dropped = TA.model_copy(
        update={"pairings": [p for p in TA.pairings if (p.agent, p.task) != ("Ravi", "L3")]}
    )
    assert messages(audit(dropped, TA_TEXT)) == [
        "The text gives Ravi → L3 = 8, but the model has no such pair."
    ]


def test_invented_route_limit_is_flagged() -> None:
    routes = [
        r.model_copy(update={"capacity": 40})
        if r.destination == "Seattle" and r.source == "Plant C"
        else r
        for r in SHIP.routes
    ]
    found = messages(audit(SHIP.model_copy(update={"routes": routes}), SHIP_TEXT))
    assert found == [
        "The model limits Plant C → Seattle to 40, but the text does not state that limit."
    ]


def test_missing_route_limit_and_blocked_route() -> None:
    routes = [r.model_copy(update={"capacity": None}) for r in SHIP.routes]
    routes.append(routes[0].model_copy(update={"destination": "Denver", "cost": 7}))
    found = messages(audit(SHIP.model_copy(update={"routes": routes}), SHIP_TEXT))
    assert any("limits Plant B → Austin to 15, but the model has no limit" in m for m in found)
    assert any("Plant C → Denver is not allowed, but the model includes it" in m for m in found)


def test_wording_checks() -> None:
    assert "The text asks to maximize, but the model minimizes." in messages(
        audit(TA.model_copy(update={"sense": "minimize"}), TA_TEXT)
    )
    at_least = SHIP_TEXT.replace("Austin requires 20", "Austin requires at least 20")
    assert any('"at least"' in m for m in messages(audit(SHIP, at_least)))


def test_generic_one_per_task_statement() -> None:
    text = "A: T1 3, T2 5. B: T1 4, T2 2. Each task needs exactly one worker. Minimize total hours."
    problem = AssignmentProblem.model_validate(
        {
            "agents": [{"id": "A"}, {"id": "B"}],
            "tasks": [{"id": "T1", "required": 2}, {"id": "T2"}],
            "pairings": [
                {"agent": "A", "task": "T1", "value": 3},
                {"agent": "A", "task": "T2", "value": 5},
                {"agent": "B", "task": "T1", "value": 4},
                {"agent": "B", "task": "T2", "value": 2},
            ],
        }
    )
    assert any("T1 has agents needed 1" in m for m in messages(audit(problem, text)))


def test_unused_number_is_flagged() -> None:
    text = SHIP_TEXT + " Delivery to Seattle has a fixed fee of 250."
    assert any("250" in m for m in messages(audit(SHIP, text)))


def test_sanity_checks_run_without_text() -> None:
    report = audit(SHIP)
    assert report.checks_run == ["structure", "sanity"]
    assert report.passed

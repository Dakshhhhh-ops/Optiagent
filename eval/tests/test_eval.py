from optiagent_core.schema import TransportationProblem
from optiagent_eval.generate import generate
from optiagent_eval.run import compare


def test_generation_is_deterministic_and_solvable() -> None:
    a, b = generate(), generate()
    assert [i.text for i in a] == [i.text for i in b]
    supported = [i for i in a if i.kind != "unsupported"]
    assert len(supported) >= 20
    assert all(i.problem is not None and i.expected_objective is not None for i in supported)


def test_generated_numbers_are_grounded_in_text() -> None:
    from optiagent_agent.grounding import ungrounded_values

    for item in generate():
        if item.problem is not None:
            assert ungrounded_values(item.problem, item.text) == [], item.id


def test_compare_finds_categorised_differences() -> None:
    truth = next(i.problem for i in generate() if isinstance(i.problem, TransportationProblem))
    assert isinstance(truth, TransportationProblem)
    assert compare(truth, truth) == []

    route = truth.routes[0]
    wrong = truth.model_copy(
        update={
            "sense": "maximize",
            "routes": [route.model_copy(update={"cost": route.cost + 1}), *truth.routes[2:]],
        }
    )
    categories = sorted(d.category for d in compare(truth, wrong))
    assert categories == ["missing_route", "wrong_route_value", "wrong_sense"]


def test_audit_catches_injected_errors_without_false_alarms() -> None:
    from optiagent_eval.mutations import evaluate

    result = evaluate()
    assert result.false_alarms == 0
    assert result.detected / result.injected >= 0.95, result.missed


def test_audit_on_hand_written_problems() -> None:
    from optiagent_eval.handwritten import items
    from optiagent_eval.mutations import evaluate

    result = evaluate(items=items())
    assert result.false_alarms == 0
    assert result.detected / result.injected >= 0.85, result.missed

"""Hand-verified instances: the solver must reproduce the known optimum and pass every check."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from optiagent_core.examples import EXAMPLES_DIR
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import ProblemSpec
from optiagent_core.solver import SolveStatus

INSTANCES = sorted(EXAMPLES_DIR.glob("*.json"))
spec_adapter: TypeAdapter[Any] = TypeAdapter(ProblemSpec)


def load(path: Path) -> tuple[dict[str, Any], Any]:
    data = json.loads(path.read_text())
    return data, spec_adapter.validate_python(data["problem"])


@pytest.mark.parametrize(
    "path", [p for p in INSTANCES if "expected_objective" in p.read_text()], ids=lambda p: p.stem
)
def test_known_optimum(path: Path) -> None:
    data, problem = load(path)
    report = solve_problem(problem)

    assert report.result.status == SolveStatus.OPTIMAL
    assert report.result.objective == pytest.approx(data["expected_objective"], abs=1e-6)
    failed = [c for c in report.verification.checks if not c.passed]
    assert report.verified, failed
    assert all(c.passed for c in report.prechecks if c.severity == "error")


@pytest.mark.parametrize(
    "path", [p for p in INSTANCES if "expected_status" in p.read_text()], ids=lambda p: p.stem
)
def test_known_status(path: Path) -> None:
    data, problem = load(path)
    report = solve_problem(problem)

    assert report.result.status == data["expected_status"]
    assert report.solution is None
    assert not report.verified
    # The data precheck must explain the failure before the solver is even consulted.
    assert any(not c.passed for c in report.prechecks if c.severity == "error")


def test_there_are_at_least_five_optimum_instances() -> None:
    assert sum("expected_objective" in p.read_text() for p in INSTANCES) >= 5

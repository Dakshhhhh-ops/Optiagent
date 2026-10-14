"""Hand-verified example problems, shared by the test suite and the UI's "load example"."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from optiagent_core.schema import AssignmentProblem, ProblemSpec, TransportationProblem

EXAMPLES_DIR = Path(__file__).parent

_spec: TypeAdapter[TransportationProblem | AssignmentProblem] = TypeAdapter(ProblemSpec)


class Example(BaseModel):
    id: str
    name: str
    kind: str
    derivation: str
    expected_objective: float | None = None
    expected_status: str | None = None
    problem: TransportationProblem | AssignmentProblem


def load_example(path: Path) -> Example:
    data: dict[str, Any] = json.loads(path.read_text())
    problem = _spec.validate_python(data["problem"])
    return Example(
        id=path.stem,
        name=problem.name,
        kind=problem.kind,
        derivation=data["derivation"],
        expected_objective=data.get("expected_objective"),
        expected_status=data.get("expected_status"),
        problem=problem,
    )


def list_examples() -> list[Example]:
    return [load_example(p) for p in sorted(EXAMPLES_DIR.glob("*.json"))]

"""Infeasibility diagnosis by elastic relaxation.

When the model has no solution, every demand / task-requirement constraint gets a shortfall
variable and we minimize total shortfall. The result says exactly which destinations or tasks
cannot be served, and by how much. This finds the smallest total violation; it is not an
irreducible infeasible subset (IIS).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from optiagent_core.model import LinearModel, Origin, Variable
from optiagent_core.solver import SolveStatus, solve

ELASTIC_KINDS = {"demand", "task_requirement"}


class Shortfall(BaseModel):
    constraint: str
    kind: str
    id: str
    required: float
    achievable: float
    shortfall: float


class Diagnosis(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    relaxed_feasible: bool
    total_shortfall: float = 0.0
    shortfalls: list[Shortfall] = Field(default_factory=list)
    explanation: str


def diagnose(model: LinearModel) -> Diagnosis:
    relaxed = model.model_copy(deep=True)
    relaxed.sense = "minimize"
    for v in relaxed.variables:
        v.objective = 0.0
    slack_of: dict[str, str] = {}
    for c in relaxed.constraints:
        if c.origin.kind in ELASTIC_KINDS and c.sense in (">=", "=="):
            name = f"short[{c.name}]"
            relaxed.variables.append(
                Variable(
                    name=name, objective=1.0, origin=Origin(kind="shortfall", keys=c.origin.keys)
                )
            )
            c.terms = {**c.terms, name: 1.0}
            slack_of[c.name] = name

    result = solve(relaxed)
    if result.status != SolveStatus.OPTIMAL:
        return Diagnosis(
            relaxed_feasible=False,
            explanation=(
                "Even allowing unmet demand, the model has no solution. Check for negative or "
                "contradictory limits."
            ),
        )

    shortfalls = []
    for c in model.constraints:
        slack_name = slack_of.get(c.name)
        if slack_name is None:
            continue
        amount = result.values.get(slack_name, 0.0)
        if amount > 1e-7:
            shortfalls.append(
                Shortfall(
                    constraint=c.name,
                    kind=c.origin.kind,
                    id=c.origin.keys[0] if c.origin.keys else c.name,
                    required=c.rhs,
                    achievable=c.rhs - amount,
                    shortfall=amount,
                )
            )
    total = sum(s.shortfall for s in shortfalls)
    unit = "position(s)" if any(s.kind == "task_requirement" for s in shortfalls) else "unit(s)"
    parts = ", ".join(f"{s.id} short by {s.shortfall:g}" for s in shortfalls)
    return Diagnosis(
        relaxed_feasible=True,
        total_shortfall=total,
        shortfalls=shortfalls,
        explanation=(
            f"At least {total:g} {unit} cannot be covered by any plan. One closest plan leaves "
            f"{parts}; other plans may spread the shortfall differently."
            if shortfalls
            else "The model is feasible."
        ),
    )

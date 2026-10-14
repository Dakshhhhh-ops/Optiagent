"""LP sensitivity analysis with HiGHS: shadow prices, reduced costs and ranging.

The model is re-solved independently with HiGHS (the primary solve uses OR-Tools GLOP), so the
two objectives must agree; that is an extra check. Duals follow the HiGHS convention: the rate of
change of the objective per unit increase of a constraint's right-hand side.

Transportation problems are often degenerate (a basic variable sits at zero). Then shadow prices
are not unique and may hold for increases only or decreases only; the ranges say which.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from optiagent_core.highs_worker import HighsResult, run_highs
from optiagent_core.model import LinearModel
from optiagent_core.solver import SolveStatus, solve

ZERO = 1e-9


class ConstraintInsight(BaseModel):
    name: str
    kind: str
    keys: tuple[str, ...]
    description: str
    activity: float
    rhs: float
    slack: float
    binding: bool
    shadow_price: float
    """Change in the objective per unit increase of the right-hand side."""
    degenerate: bool = False
    """Tight but basic: the shadow price may hold in one direction only."""
    rhs_from: float | None
    rhs_to: float | None
    """The shadow price holds while the right-hand side stays in [rhs_from, rhs_to]."""
    change_if_increased: float | None = None
    change_if_decreased: float | None = None
    """Exact objective change for one more / one less unit, by re-solving (None = infeasible)."""


class VariableInsight(BaseModel):
    name: str
    kind: str
    keys: tuple[str, ...]
    value: float
    cost: float
    reduced_cost: float
    status: Literal["basic", "at_lower", "at_upper"]
    cost_from: float | None
    cost_to: float | None
    """The current plan stays optimal while this cost stays in [cost_from, cost_to]."""


class Sensitivity(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    available: bool
    reason: str | None = None
    objective: float | None = None
    degenerate: bool = False
    constraints: list[ConstraintInsight] = Field(default_factory=list)
    variables: list[VariableInsight] = Field(default_factory=list)


_pool: ProcessPoolExecutor | None = None


def _highs(model: LinearModel) -> HighsResult:
    """Run HiGHS in a long-lived worker process (see highs_worker for why)."""
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
    return _pool.submit(run_highs, model.model_dump_json()).result(timeout=120)


def _one_unit_change(model: LinearModel, row: int, delta: float, base: float) -> float | None:
    """Objective change when one constraint's right-hand side moves by `delta`, by re-solving."""
    if model.constraints[row].rhs + delta < 0:
        return None
    changed = model.model_copy(deep=True)
    changed.constraints[row].rhs += delta
    result = solve(changed)
    if result.status != SolveStatus.OPTIMAL or result.objective is None:
        return None
    return result.objective - base


def analyze_sensitivity(model: LinearModel) -> Sensitivity:
    if model.is_mip:
        return Sensitivity(available=False, reason="Duals only exist for linear programs.")

    h = _highs(model)
    if not h.optimal:
        return Sensitivity(available=False, reason=f"HiGHS status: {h.status}")
    if not h.ranging_ok:
        return Sensitivity(available=False, reason="Ranging is not available for this model.")

    objective = h.objective
    col_value, col_dual, row_value, row_dual = h.col_value, h.col_dual, h.row_value, h.row_dual

    variables = []
    degenerate = False
    for i, v in enumerate(model.variables):
        basic = h.col_basic[i]
        if basic and abs(col_value[i]) <= ZERO:
            degenerate = True
        at_upper = h.col_at_upper[i]
        variables.append(
            VariableInsight(
                name=v.name,
                kind=v.origin.kind,
                keys=v.origin.keys,
                value=col_value[i],
                cost=v.objective,
                reduced_cost=col_dual[i],
                status="basic" if basic else ("at_upper" if at_upper else "at_lower"),
                cost_from=h.cost_dn[i],
                cost_to=h.cost_up[i],
            )
        )

    constraints = []
    for r, c in enumerate(model.constraints):
        slack = c.rhs - row_value[r] if c.sense == "<=" else row_value[r] - c.rhs
        if c.sense == "==":
            slack = 0.0
        # A constraint that is tight but still basic is degenerate: its dual is not a reliable
        # two-sided price and HiGHS's range does not describe its right-hand side. Report no
        # range and rely on the exact one-unit re-solves instead.
        row_degenerate = h.row_basic[r] and abs(slack) <= ZERO
        degenerate = degenerate or row_degenerate
        constraints.append(
            ConstraintInsight(
                name=c.name,
                kind=c.origin.kind,
                keys=c.origin.keys,
                description=c.description,
                activity=row_value[r],
                rhs=c.rhs,
                slack=max(slack, 0.0),
                binding=abs(slack) <= 1e-7 * max(1.0, abs(c.rhs)),
                shadow_price=row_dual[r],
                degenerate=row_degenerate,
                rhs_from=None if row_degenerate else h.rhs_dn[r],
                rhs_to=None if row_degenerate else h.rhs_up[r],
            )
        )

    for r, insight in enumerate(constraints):
        if insight.binding:
            insight.change_if_increased = _one_unit_change(model, r, +1.0, base=objective)
            insight.change_if_decreased = _one_unit_change(model, r, -1.0, base=objective)

    return Sensitivity(
        available=True,
        objective=objective,
        degenerate=degenerate,
        constraints=constraints,
        variables=variables,
    )

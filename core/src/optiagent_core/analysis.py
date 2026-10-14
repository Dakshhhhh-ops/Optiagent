"""LP sensitivity analysis with HiGHS: shadow prices, reduced costs and ranging.

The model is re-solved independently with HiGHS (the primary solve uses OR-Tools GLOP), so the
two objectives must agree; that is an extra check. Duals follow the HiGHS convention: the rate of
change of the objective per unit increase of a constraint's right-hand side.

Transportation problems are often degenerate (a basic variable sits at zero). Then shadow prices
are not unique and may hold for increases only or decreases only; the ranges say which.
"""

from __future__ import annotations

import math
from typing import Literal

# OR-Tools bundles its own HiGHS. On Linux, if highspy's HiGHS is loaded first, libortools
# binds to the wrong symbols and fails to import. Load OR-Tools first.
from ortools.linear_solver import pywraplp  # noqa: F401  # isort: skip

import highspy  # isort: skip
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

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


def _finite(x: float) -> float | None:
    return None if math.isinf(x) or abs(x) >= highspy.kHighsInf else float(x)


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

    h = highspy.Highs()  # type: ignore[no-untyped-call]
    h.setOptionValue("output_flag", False)
    inf = highspy.kHighsInf
    n = len(model.variables)
    index = {v.name: i for i, v in enumerate(model.variables)}

    h.addVars(
        n,
        np.array([v.lb for v in model.variables], dtype=np.float64),
        np.array([inf if v.ub is None else v.ub for v in model.variables], dtype=np.float64),
    )
    h.changeColsCost(
        n,
        np.arange(n, dtype=np.int32),
        np.array([v.objective for v in model.variables], dtype=np.float64),
    )
    for c in model.constraints:
        lower = -inf if c.sense == "<=" else c.rhs
        upper = inf if c.sense == ">=" else c.rhs
        cols = np.array([index[name] for name in c.terms], dtype=np.int32)
        vals = np.array(list(c.terms.values()), dtype=np.float64)
        h.addRow(lower, upper, len(cols), cols, vals)
    if model.sense == "maximize":
        h.changeObjectiveSense(highspy.ObjSense.kMaximize)

    h.run()
    if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
        return Sensitivity(
            available=False, reason=f"HiGHS status: {h.modelStatusToString(h.getModelStatus())}"
        )

    solution = h.getSolution()
    basis = h.getBasis()
    status, ranging = h.getRanging()
    if status != highspy.HighsStatus.kOk:
        return Sensitivity(available=False, reason="Ranging is not available for this model.")

    objective = h.getInfo().objective_function_value
    col_value = list(solution.col_value)
    row_value = list(solution.row_value)
    row_dual = list(solution.row_dual)
    col_dual = list(solution.col_dual)

    variables = []
    degenerate = False
    for i, v in enumerate(model.variables):
        basic = basis.col_status[i] == highspy.HighsBasisStatus.kBasic
        if basic and abs(col_value[i]) <= ZERO:
            degenerate = True
        at_upper = basis.col_status[i] == highspy.HighsBasisStatus.kUpper
        variables.append(
            VariableInsight(
                name=v.name,
                kind=v.origin.kind,
                keys=v.origin.keys,
                value=col_value[i],
                cost=v.objective,
                reduced_cost=col_dual[i],
                status="basic" if basic else ("at_upper" if at_upper else "at_lower"),
                cost_from=_finite(ranging.col_cost_dn.value_[i]),
                cost_to=_finite(ranging.col_cost_up.value_[i]),
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
        row_degenerate = (
            basis.row_status[r] == highspy.HighsBasisStatus.kBasic and abs(slack) <= ZERO
        )
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
                rhs_from=None if row_degenerate else _finite(ranging.row_bound_dn.value_[r]),
                rhs_to=None if row_degenerate else _finite(ranging.row_bound_up.value_[r]),
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

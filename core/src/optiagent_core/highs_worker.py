"""HiGHS solve + ranging, run in a separate process.

OR-Tools and highspy both ship their own HiGHS library. On Linux they cannot be loaded into the
same process (whichever loads second fails with undefined symbols), so the analysis runs HiGHS
in a worker process that never imports OR-Tools. This module must not import OR-Tools, directly
or through optiagent_core.solver / pipeline.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from optiagent_core.model import LinearModel


class HighsResult(BaseModel):
    optimal: bool
    status: str
    objective: float = 0.0
    col_value: list[float] = []
    col_dual: list[float] = []
    row_value: list[float] = []
    row_dual: list[float] = []
    col_basic: list[bool] = []
    col_at_upper: list[bool] = []
    row_basic: list[bool] = []
    cost_dn: list[float | None] = []
    cost_up: list[float | None] = []
    rhs_dn: list[float | None] = []
    rhs_up: list[float | None] = []
    ranging_ok: bool = False


def run_highs(model_json: str) -> HighsResult:
    import highspy  # imported here so importing this module stays cheap and OR-Tools-free
    import numpy as np

    model = LinearModel.model_validate_json(model_json)
    inf = highspy.kHighsInf

    def finite(x: float) -> float | None:
        return None if math.isinf(x) or abs(x) >= inf else float(x)

    h = highspy.Highs()  # type: ignore[no-untyped-call]
    h.setOptionValue("output_flag", False)
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
    status = h.getModelStatus()
    if status != highspy.HighsModelStatus.kOptimal:
        return HighsResult(optimal=False, status=h.modelStatusToString(status))

    solution = h.getSolution()
    basis = h.getBasis()
    ranging_status, ranging = h.getRanging()
    ok = ranging_status == highspy.HighsStatus.kOk
    m = len(model.constraints)
    return HighsResult(
        optimal=True,
        status="optimal",
        objective=h.getInfo().objective_function_value,
        col_value=list(solution.col_value),
        col_dual=list(solution.col_dual),
        row_value=list(solution.row_value),
        row_dual=list(solution.row_dual),
        col_basic=[s == highspy.HighsBasisStatus.kBasic for s in basis.col_status],
        col_at_upper=[s == highspy.HighsBasisStatus.kUpper for s in basis.col_status],
        row_basic=[s == highspy.HighsBasisStatus.kBasic for s in basis.row_status],
        cost_dn=[finite(ranging.col_cost_dn.value_[i]) for i in range(n)] if ok else [],
        cost_up=[finite(ranging.col_cost_up.value_[i]) for i in range(n)] if ok else [],
        rhs_dn=[finite(ranging.row_bound_dn.value_[r]) for r in range(m)] if ok else [],
        rhs_up=[finite(ranging.row_bound_up.value_[r]) for r in range(m)] if ok else [],
        ranging_ok=ok,
    )

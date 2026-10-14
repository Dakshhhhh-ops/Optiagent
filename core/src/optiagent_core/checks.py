"""Layer 1 verification: re-check a solution against the model, independently of the solver.

These checks never call the solver. They only read the LinearModel and the returned values,
so a bug in the solver wrapper (wrong sign, dropped constraint, mis-mapped variable) shows up
as a failed check instead of a silently wrong answer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field

from optiagent_core.model import LinearModel
from optiagent_core.solver import SolveResult, SolveStatus

DEFAULT_TOL = 1e-6


class Check(BaseModel):
    name: str
    passed: bool
    severity: Literal["error", "warning"] = "error"
    detail: str = ""


class CheckReport(BaseModel):
    checks: list[Check]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "error")


def _scaled_tol(value: float, tol: float) -> float:
    return tol * max(1.0, abs(value))


def verify_solution(
    model: LinearModel, result: SolveResult, tol: float = DEFAULT_TOL
) -> CheckReport:
    checks = [
        Check(
            name="solver_status",
            passed=result.status == SolveStatus.OPTIMAL,
            detail=f"status = {result.status}",
        )
    ]
    if not result.has_solution:
        return CheckReport(checks=checks)

    values = result.values

    missing = [v.name for v in model.variables if v.name not in values]
    checks.append(
        Check(
            name="all_variables_reported",
            passed=not missing,
            detail=f"missing: {', '.join(missing[:5])}" if missing else "",
        )
    )

    bound_violations = []
    integrality_violations = []
    for v in model.variables:
        x = values.get(v.name, 0.0)
        if x < v.lb - _scaled_tol(v.lb, tol) or (
            v.ub is not None and x > v.ub + _scaled_tol(v.ub, tol)
        ):
            bound_violations.append(f"{v.name}={x:g} not in [{v.lb:g}, {v.ub}]")
        if (v.integer or v.expect_integral) and abs(x - round(x)) > tol:
            integrality_violations.append(f"{v.name}={x:g}")
    checks.append(
        Check(
            name="variable_bounds",
            passed=not bound_violations,
            detail="; ".join(bound_violations[:5]),
        )
    )
    checks.append(
        Check(
            name="integrality",
            passed=not integrality_violations,
            detail="; ".join(integrality_violations[:5]),
        )
    )

    constraint_violations = []
    for c in model.constraints:
        lhs = model.activity(c, values)
        slack = _scaled_tol(c.rhs, tol)
        ok = (
            (c.sense == "<=" and lhs <= c.rhs + slack)
            or (c.sense == ">=" and lhs >= c.rhs - slack)
            or (c.sense == "==" and abs(lhs - c.rhs) <= slack)
        )
        if not ok:
            constraint_violations.append(f"{c.name}: {lhs:g} {c.sense} {c.rhs:g}")
    checks.append(
        Check(
            name="constraints_satisfied",
            passed=not constraint_violations,
            detail="; ".join(constraint_violations[:5])
            or f"{len(model.constraints)} constraints hold",
        )
    )

    recomputed = model.objective_value(values)
    reported = result.objective if result.objective is not None else float("nan")
    checks.append(
        Check(
            name="objective_recomputed",
            passed=abs(recomputed - reported) <= _scaled_tol(recomputed, tol),
            detail=f"recomputed {recomputed:.6g} vs solver {reported:.6g}",
        )
    )

    return CheckReport(checks=checks)

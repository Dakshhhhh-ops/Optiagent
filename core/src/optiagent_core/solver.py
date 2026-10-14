"""Solve a LinearModel with OR-Tools."""

from __future__ import annotations

import time
from enum import StrEnum

from ortools.linear_solver import pywraplp
from pydantic import BaseModel, Field

from optiagent_core.model import LinearModel


class SolveStatus(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    ERROR = "error"


_STATUS = {
    pywraplp.Solver.OPTIMAL: SolveStatus.OPTIMAL,
    pywraplp.Solver.FEASIBLE: SolveStatus.FEASIBLE,
    pywraplp.Solver.INFEASIBLE: SolveStatus.INFEASIBLE,
    pywraplp.Solver.UNBOUNDED: SolveStatus.UNBOUNDED,
}


class SolveResult(BaseModel):
    status: SolveStatus
    solver: str
    objective: float | None = None
    values: dict[str, float] = Field(default_factory=dict)
    duals: dict[str, float] = Field(default_factory=dict)
    """Constraint name -> dual value (LP only). Rate of change of the objective per unit of rhs."""
    reduced_costs: dict[str, float] = Field(default_factory=dict)
    wall_time_ms: float = 0.0

    @property
    def has_solution(self) -> bool:
        return self.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)


def solve(model: LinearModel, backend: str | None = None) -> SolveResult:
    """Solve with GLOP for LPs and SCIP for MIPs unless a backend is given."""
    backend = backend or ("SCIP" if model.is_mip else "GLOP")
    solver = pywraplp.Solver.CreateSolver(backend)
    if solver is None:
        raise RuntimeError(f"OR-Tools backend {backend!r} is not available")

    inf = solver.infinity()
    variables = {}
    for v in model.variables:
        ub = inf if v.ub is None else v.ub
        variables[v.name] = (
            solver.IntVar(v.lb, ub, v.name) if v.integer else solver.NumVar(v.lb, ub, v.name)
        )

    constraints = {}
    for c in model.constraints:
        lb = -inf if c.sense == "<=" else c.rhs
        ub = inf if c.sense == ">=" else c.rhs
        ct = solver.Constraint(lb, ub, c.name)
        for name, coef in c.terms.items():
            ct.SetCoefficient(variables[name], coef)
        constraints[c.name] = ct

    objective = solver.Objective()
    for v in model.variables:
        objective.SetCoefficient(variables[v.name], v.objective)
    if model.sense == "minimize":
        objective.SetMinimization()
    else:
        objective.SetMaximization()

    start = time.perf_counter()
    code = solver.Solve()
    elapsed = (time.perf_counter() - start) * 1000

    status = _STATUS.get(code, SolveStatus.ERROR)
    result = SolveResult(status=status, solver=backend, wall_time_ms=elapsed)
    if not result.has_solution:
        return result

    result.objective = objective.Value()
    result.values = {name: var.solution_value() for name, var in variables.items()}
    if not model.is_mip:
        result.duals = {name: ct.dual_value() for name, ct in constraints.items()}
        result.reduced_costs = {name: var.reduced_cost() for name, var in variables.items()}
    return result

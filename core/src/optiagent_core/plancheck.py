"""Problem-level verification: check a plan against the original problem data.

Layer 1 (checks.py) re-checks the solver's answer against the LinearModel. That cannot catch a
bug in the model builder itself: a dropped constraint or a flipped sign would be checked against
the same wrong model. These checks never read the LinearModel. They recompute every shipment
total, staffing count and the objective directly from the typed problem (the data the user
approved), using only the variable naming convention to read the plan.

Tolerance: a quantity passes when it is within 1e-6 x max(1, |reference|) of its limit.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from optiagent_core.builders import assign_var, flow_var
from optiagent_core.checks import Check
from optiagent_core.schema import AssignmentProblem, TransportationProblem

PLAN_TOL = 1e-6
MAX_DETAILS = 5


def _tol(reference: float) -> float:
    return PLAN_TOL * max(1.0, abs(reference))


def _check(name: str, problems: list[str], ok_detail: str) -> Check:
    return Check(
        name=name,
        passed=not problems,
        scope="problem",
        detail="; ".join(problems[:MAX_DETAILS])
        + (f" (+{len(problems) - MAX_DETAILS} more)" if len(problems) > MAX_DETAILS else "")
        if problems
        else ok_detail,
    )


def _plan_values(
    expected: set[str], values: dict[str, float]
) -> tuple[list[Check], dict[str, float]]:
    unknown = sorted(set(values) - expected)
    missing = sorted(expected - set(values))
    not_finite = sorted(n for n, x in values.items() if not math.isfinite(x))
    checks = [
        _check(
            "plan_covers_allowed_pairs_only",
            [f"value for a pair that is not allowed: {n}" for n in unknown]
            + [f"no value for {n}" for n in missing],
            f"{len(expected)} allowed pairs, no others",
        ),
        _check("plan_values_finite", [f"{n} = {values[n]}" for n in not_finite], "all finite"),
    ]
    clean = {n: values.get(n, 0.0) for n in expected if n not in not_finite}
    return checks, clean


def _objective_check(recomputed: float, reported: float | None) -> Check:
    if reported is None or not math.isfinite(reported):
        return _check("plan_objective_from_data", [f"solver objective is {reported}"], "")
    gap = abs(recomputed - reported)
    return _check(
        "plan_objective_from_data",
        [f"recomputed {recomputed:.9g} from the data, solver reported {reported:.9g}"]
        if gap > _tol(recomputed)
        else [],
        f"recomputed {recomputed:.9g} from the data, matches the solver",
    )


def check_transportation_plan(
    problem: TransportationProblem, values: dict[str, float], objective: float | None
) -> list[Check]:
    names = {flow_var(r.source, r.destination): r for r in problem.routes}
    checks, plan = _plan_values(set(names), values)

    shipped: dict[str, float] = defaultdict(float)
    received: dict[str, float] = defaultdict(float)
    bounds = []
    total = 0.0
    for name, q in plan.items():
        r = names[name]
        if q < -_tol(0.0):
            bounds.append(f"{r.source} → {r.destination} ships {q:g} (negative)")
        if r.capacity is not None and q > r.capacity + _tol(r.capacity):
            bounds.append(f"{r.source} → {r.destination} ships {q:g} over its limit {r.capacity:g}")
        shipped[r.source] += q
        received[r.destination] += q
        total += q * r.cost
    checks.append(_check("plan_route_limits", bounds, "no negative or over-limit shipments"))

    checks.append(
        _check(
            "plan_supply_respected",
            [
                f"{s.id} ships {shipped[s.id]:g} but has only {s.supply:g}"
                for s in problem.sources
                if shipped[s.id] > s.supply + _tol(s.supply)
            ],
            f"all {len(problem.sources)} sources within supply",
        )
    )
    exact = problem.demand_constraint == "equal"
    short = []
    for d in problem.destinations:
        got = received[d.id]
        if got < d.demand - _tol(d.demand) or (exact and got > d.demand + _tol(d.demand)):
            short.append(
                f"{d.id} receives {got:g}, needs {'exactly' if exact else 'at least'} {d.demand:g}"
            )
    checks.append(
        _check("plan_demand_met", short, f"all {len(problem.destinations)} destinations served")
    )
    checks.append(_objective_check(total, objective))
    return checks


def check_assignment_plan(
    problem: AssignmentProblem, values: dict[str, float], objective: float | None
) -> list[Check]:
    names = {assign_var(p.agent, p.task): p for p in problem.pairings}
    checks, plan = _plan_values(set(names), values)

    load: dict[str, int] = defaultdict(int)
    staffed: dict[str, int] = defaultdict(int)
    fractional = []
    total = 0.0
    for name, y in plan.items():
        p = names[name]
        if abs(y) <= PLAN_TOL:
            continue
        if abs(y - 1.0) > PLAN_TOL:
            fractional.append(f"{p.agent} → {p.task} = {y:g}")
            continue
        load[p.agent] += 1
        staffed[p.task] += 1
        total += p.value
    checks.append(_check("plan_whole_assignments", fractional, "every pair is 0 or 1"))
    checks.append(
        _check(
            "plan_agent_capacity",
            [
                f"{a.id} has {load[a.id]} task(s), capacity {a.capacity}"
                for a in problem.agents
                if load[a.id] > a.capacity
            ],
            f"all {len(problem.agents)} agents within capacity",
        )
    )
    checks.append(
        _check(
            "plan_task_staffing",
            [
                f"{t.id} has {staffed[t.id]} agent(s), needs exactly {t.required}"
                for t in problem.tasks
                if staffed[t.id] != t.required
            ],
            f"all {len(problem.tasks)} tasks staffed exactly",
        )
    )
    checks.append(_objective_check(total, objective))
    return checks


# --------------------------------------------------------------------------- optimality certificate


class _Row(BaseModel):
    name: str
    sense: Literal["<=", ">=", "=="]
    rhs: float


class _Col(BaseModel):
    name: str
    cost: float
    ub: float | None
    rows: tuple[str, str]


def _structure(problem: TransportationProblem | AssignmentProblem) -> tuple[list[_Row], list[_Col]]:
    """The LP written directly from the problem data (not from the model builder's output)."""
    if isinstance(problem, TransportationProblem):
        demand: Literal["==", ">="] = "==" if problem.demand_constraint == "equal" else ">="
        rows = [_Row(name=f"supply[{s.id}]", sense="<=", rhs=s.supply) for s in problem.sources]
        rows += [_Row(name=f"demand[{d.id}]", sense=demand, rhs=d.demand) for d in problem.destinations]  # fmt: skip
        cols = [
            _Col(name=flow_var(r.source, r.destination), cost=r.cost, ub=r.capacity,
                 rows=(f"supply[{r.source}]", f"demand[{r.destination}]"))
            for r in problem.routes
        ]  # fmt: skip
        return rows, cols
    rows = [_Row(name=f"capacity[{a.id}]", sense="<=", rhs=a.capacity) for a in problem.agents]
    rows += [_Row(name=f"cover[{t.id}]", sense="==", rhs=t.required) for t in problem.tasks]
    cols = [
        _Col(name=assign_var(p.agent, p.task), cost=p.value, ub=1.0,
             rows=(f"capacity[{p.agent}]", f"cover[{p.task}]"))
        for p in problem.pairings
    ]  # fmt: skip
    return rows, cols


def _dual_bound(rows: list[_Row], cols: list[_Col], prices: dict[str, float], sign: float) -> float:
    """Lagrangian lower bound for min c'x (weak duality). Valid for ANY prices once their signs
    are clipped to the row type, so the solver's duals are only a hint, never trusted."""
    y: dict[str, float] = {}
    for r in rows:
        p = sign * prices.get(r.name, 0.0)
        y[r.name] = min(p, 0.0) if r.sense == "<=" else max(p, 0.0) if r.sense == ">=" else p
    bound = sum(y[r.name] * r.rhs for r in rows)
    for c in cols:
        reduced = c.cost - y[c.rows[0]] - y[c.rows[1]]
        if reduced < 0:
            if c.ub is None:
                return -math.inf
            bound += reduced * c.ub
    return bound


def check_optimality(
    problem: TransportationProblem | AssignmentProblem,
    values: dict[str, float],
    duals: dict[str, float],
) -> Check:
    """Prove the plan optimal from the problem data alone: its cost must equal a dual bound.

    Weak duality: no feasible plan costs less than the bound, whatever prices produced it. So
    a plan whose cost meets the bound is optimal for the data, even if the model builder or the
    solver were wrong. The check fails when no such bound is found (the plan may be suboptimal).
    """
    rows, cols = _structure(problem)
    flip = -1.0 if problem.sense == "maximize" else 1.0  # work with minimize c'x
    rows_min = rows
    cols_min = [c.model_copy(update={"cost": flip * c.cost}) for c in cols]
    plan = sum(c.cost * values.get(c.name, 0.0) for c in cols_min)
    if not duals:
        return Check(
            name="plan_optimality_certificate", passed=False, severity="warning", scope="problem",
            detail="no dual prices available, optimality not certified from the data",
        )  # fmt: skip
    bound = max(_dual_bound(rows_min, cols_min, duals, s) for s in (1.0, -1.0))
    gap = plan - bound
    word = "cost" if problem.sense == "minimize" else "value"
    if gap <= _tol(plan):
        detail = f"no plan can do better: the plan's {word} equals a bound proven from the data"
        return Check(
            name="plan_optimality_certificate", passed=True, scope="problem", detail=detail
        )
    shown = "unbounded" if math.isinf(bound) else f"{flip * bound:.9g}"
    return Check(
        name="plan_optimality_certificate", passed=False, scope="problem",
        detail=f"not proven optimal: the plan's {word} is {flip * plan:.9g}, the best bound from the data is {shown}",
    )  # fmt: skip


def check_plan(
    problem: TransportationProblem | AssignmentProblem,
    values: dict[str, float],
    objective: float | None,
    duals: dict[str, float] | None = None,
) -> list[Check]:
    """Feasibility and objective against the data; with `duals`, also certify optimality."""
    checks = (
        check_transportation_plan(problem, values, objective)
        if isinstance(problem, TransportationProblem)
        else check_assignment_plan(problem, values, objective)
    )
    if duals is not None:
        checks.append(check_optimality(problem, values, duals))
    return checks

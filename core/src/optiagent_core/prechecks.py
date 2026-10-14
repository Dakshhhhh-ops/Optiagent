"""Data consistency checks that run before solving.

They catch the common, explainable reasons a model has no solution, so the user gets
"total supply 450 is below total demand 500" instead of a bare INFEASIBLE.
"""

from __future__ import annotations

from collections import defaultdict
from functools import singledispatch

from optiagent_core.checks import Check
from optiagent_core.schema import AssignmentProblem, TransportationProblem


@singledispatch
def precheck(problem: object) -> list[Check]:
    return []


@precheck.register
def _(problem: TransportationProblem) -> list[Check]:
    checks = []
    total_supply = sum(s.supply for s in problem.sources)
    total_demand = sum(d.demand for d in problem.destinations)
    checks.append(
        Check(
            name="supply_covers_demand",
            passed=total_supply >= total_demand,
            detail=f"total supply {total_supply:g}, total demand {total_demand:g}",
        )
    )

    inbound_capacity: dict[str, float] = defaultdict(float)
    reachable: dict[str, float] = defaultdict(float)
    supply = {s.id: s.supply for s in problem.sources}
    for r in problem.routes:
        cap = supply[r.source] if r.capacity is None else min(r.capacity, supply[r.source])
        inbound_capacity[r.destination] += cap
        reachable[r.destination] += 1

    unreachable = [d.id for d in problem.destinations if d.demand > 0 and not reachable[d.id]]
    checks.append(
        Check(
            name="every_destination_reachable",
            passed=not unreachable,
            detail=f"no route into: {', '.join(unreachable)}" if unreachable else "",
        )
    )

    short = [
        f"{d.id} needs {d.demand:g}, routes can bring at most {inbound_capacity[d.id]:g}"
        for d in problem.destinations
        if reachable[d.id] and inbound_capacity[d.id] < d.demand
    ]
    checks.append(
        Check(
            name="inbound_capacity_covers_demand",
            passed=not short,
            detail="; ".join(short),
        )
    )

    if total_supply > total_demand and problem.demand_constraint == "equal":
        checks.append(
            Check(
                name="unbalanced_problem",
                passed=False,
                severity="warning",
                detail=f"{total_supply - total_demand:g} units of supply will stay unused",
            )
        )
    return checks


@precheck.register
def _(problem: AssignmentProblem) -> list[Check]:
    checks = []
    total_capacity = sum(a.capacity for a in problem.agents)
    total_required = sum(t.required for t in problem.tasks)
    checks.append(
        Check(
            name="capacity_covers_requirements",
            passed=total_capacity >= total_required,
            detail=f"agents can take {total_capacity} slots, tasks need {total_required}",
        )
    )

    eligible: dict[str, int] = defaultdict(int)
    for p in problem.pairings:
        eligible[p.task] += 1
    understaffed = [
        f"{t.id} needs {t.required}, only {eligible[t.id]} eligible"
        for t in problem.tasks
        if eligible[t.id] < t.required
    ]
    checks.append(
        Check(
            name="enough_eligible_agents",
            passed=not understaffed,
            detail="; ".join(understaffed),
        )
    )
    return checks

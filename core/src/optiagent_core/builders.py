"""Deterministic builders: typed problem -> LinearModel."""

from __future__ import annotations

from collections import defaultdict
from functools import singledispatch

from optiagent_core.model import Constraint, LinearModel, Origin, Sense, Variable
from optiagent_core.schema import AssignmentProblem, TransportationProblem


def flow_var(source: str, destination: str) -> str:
    return f"x[{source},{destination}]"


def assign_var(agent: str, task: str) -> str:
    return f"y[{agent},{task}]"


@singledispatch
def build_model(problem: object) -> LinearModel:
    raise TypeError(f"no model builder for {type(problem).__name__}")


@build_model.register
def _(problem: TransportationProblem) -> LinearModel:
    model = LinearModel(name=problem.name, sense=problem.sense)
    out_of: dict[str, dict[str, float]] = defaultdict(dict)
    into: dict[str, dict[str, float]] = defaultdict(dict)

    for r in problem.routes:
        name = flow_var(r.source, r.destination)
        out_of[r.source][name] = 1.0
        into[r.destination][name] = 1.0
        model.variables.append(
            Variable(
                name=name,
                ub=r.capacity,
                objective=r.cost,
                origin=Origin(kind="route", keys=(r.source, r.destination)),
            )
        )

    for s in problem.sources:
        model.constraints.append(
            Constraint(
                name=f"supply[{s.id}]",
                terms=out_of[s.id],
                sense="<=",
                rhs=s.supply,
                origin=Origin(kind="supply", keys=(s.id,)),
                description=f"Ship at most {s.supply:g} out of {s.id}",
            )
        )

    demand_sense: Sense = "==" if problem.demand_constraint == "equal" else ">="
    for d in problem.destinations:
        wording = "exactly" if demand_sense == "==" else "at least"
        model.constraints.append(
            Constraint(
                name=f"demand[{d.id}]",
                terms=into[d.id],
                sense=demand_sense,
                rhs=d.demand,
                origin=Origin(kind="demand", keys=(d.id,)),
                description=f"Deliver {wording} {d.demand:g} to {d.id}",
            )
        )

    return model


@build_model.register
def _(problem: AssignmentProblem) -> LinearModel:
    model = LinearModel(name=problem.name, sense=problem.sense)
    by_agent: dict[str, dict[str, float]] = defaultdict(dict)
    by_task: dict[str, dict[str, float]] = defaultdict(dict)

    for p in problem.pairings:
        name = assign_var(p.agent, p.task)
        by_agent[p.agent][name] = 1.0
        by_task[p.task][name] = 1.0
        model.variables.append(
            Variable(
                name=name,
                ub=1.0,
                expect_integral=True,
                objective=p.value,
                origin=Origin(kind="pairing", keys=(p.agent, p.task)),
            )
        )

    for a in problem.agents:
        model.constraints.append(
            Constraint(
                name=f"capacity[{a.id}]",
                terms=by_agent[a.id],
                sense="<=",
                rhs=a.capacity,
                origin=Origin(kind="agent_capacity", keys=(a.id,)),
                description=f"{a.id} takes at most {a.capacity} task(s)",
            )
        )

    for t in problem.tasks:
        model.constraints.append(
            Constraint(
                name=f"cover[{t.id}]",
                terms=by_task[t.id],
                sense="==",
                rhs=t.required,
                origin=Origin(kind="task_requirement", keys=(t.id,)),
                description=f"{t.id} gets exactly {t.required} agent(s)",
            )
        )

    return model

"""Deterministic plain-English and LaTeX rendering of a problem, for human confirmation.

The user approves exactly what will be solved, so this is generated from the typed problem
and the built model by code, never written by the LLM.
"""

from __future__ import annotations

from pydantic import BaseModel

from optiagent_core.builders import build_model
from optiagent_core.schema import AssignmentProblem, TransportationProblem


class SetDef(BaseModel):
    symbol: str
    name: str
    members: list[str]


class ConstraintGroup(BaseModel):
    name: str
    english: str
    latex: str
    items: list[str]
    """One concrete line per constraint, with the actual numbers."""


class Formulation(BaseModel):
    title: str
    objective_english: str
    objective_latex: str
    sets: list[SetDef]
    constraints: list[ConstraintGroup]
    domain_latex: str
    notes: list[str]


def _fmt(x: float) -> str:
    return f"{x:,.10g}"


def _transportation(p: TransportationProblem) -> Formulation:
    model = build_model(p)
    by_kind: dict[str, list[str]] = {}
    for c in model.constraints:
        by_kind.setdefault(c.origin.kind, []).append(c.description)

    sources = [s.id for s in p.sources]
    destinations = [d.id for d in p.destinations]
    blocked = len(sources) * len(destinations) - len(p.routes)
    capped = [r for r in p.routes if r.capacity is not None]
    total_supply = sum(s.supply for s in p.sources)
    total_demand = sum(d.demand for d in p.destinations)
    exact = p.demand_constraint == "equal"
    verb = "Minimize" if p.sense == "minimize" else "Maximize"

    notes = []
    if blocked:
        notes.append(f"{blocked} source–destination pair(s) are not allowed and get no variable.")
    if capped:
        notes.append(f"{len(capped)} route(s) have a maximum quantity.")
    if total_supply > total_demand:
        notes.append(
            f"Total supply {_fmt(total_supply)} exceeds total demand {_fmt(total_demand)}; "
            f"{_fmt(total_supply - total_demand)} units can stay unused."
        )
    elif total_supply < total_demand:
        notes.append(
            f"Total supply {_fmt(total_supply)} is below total demand {_fmt(total_demand)}; "
            "the model will be infeasible."
        )
    if not exact:
        notes.append("Destinations may receive more than their demand if that is cheaper.")

    sense_tex = r"\min" if p.sense == "minimize" else r"\max"
    return Formulation(
        title=p.name,
        objective_english=(
            f"{verb} the total of cost per unit × quantity shipped over the "
            f"{len(p.routes)} allowed routes."
        ),
        objective_latex=sense_tex + r" \sum_{(i,j) \in R} c_{ij}\, x_{ij}",
        sets=[
            SetDef(symbol="S", name="Sources", members=sources),
            SetDef(symbol="D", name="Destinations", members=destinations),
            SetDef(
                symbol="R",
                name="Allowed routes",
                members=[f"{r.source}→{r.destination}" for r in p.routes],
            ),
        ],
        constraints=[
            ConstraintGroup(
                name="Supply",
                english="Each source ships no more than its supply.",
                latex=r"\sum_{j:(i,j) \in R} x_{ij} \le s_i \quad \forall i \in S",
                items=by_kind.get("supply", []),
            ),
            ConstraintGroup(
                name="Demand",
                english=(
                    "Each destination receives exactly its demand."
                    if exact
                    else "Each destination receives at least its demand."
                ),
                latex=(
                    r"\sum_{i:(i,j) \in R} x_{ij} "
                    + ("=" if exact else r"\ge")
                    + r" d_j \quad \forall j \in D"
                ),
                items=by_kind.get("demand", []),
            ),
            *(
                [
                    ConstraintGroup(
                        name="Route capacity",
                        english="Some routes carry at most a fixed quantity.",
                        latex=r"x_{ij} \le u_{ij} \quad \forall (i,j) \in R_{\text{cap}}",
                        items=[
                            f"Ship at most {_fmt(r.capacity or 0)} "
                            f"from {r.source} to {r.destination}"
                            for r in capped
                        ],
                    )
                ]
                if capped
                else []
            ),
        ],
        domain_latex=r"x_{ij} \ge 0 \quad \forall (i,j) \in R",
        notes=notes,
    )


def _assignment(p: AssignmentProblem) -> Formulation:
    model = build_model(p)
    by_kind: dict[str, list[str]] = {}
    for c in model.constraints:
        by_kind.setdefault(c.origin.kind, []).append(c.description)

    agents = [a.id for a in p.agents]
    tasks = [t.id for t in p.tasks]
    blocked = len(agents) * len(tasks) - len(p.pairings)
    slots = sum(a.capacity for a in p.agents)
    needed = sum(t.required for t in p.tasks)
    minimize = p.sense == "minimize"

    notes = [
        "Solved as a linear program: with whole-number capacities and requirements the best "
        "solution is automatically whole (each pair is 0 or 1), and a check confirms it."
    ]
    if blocked:
        notes.insert(0, f"{blocked} agent–task pair(s) are not allowed and get no variable.")
    if slots < needed:
        notes.append(
            f"Agents can fill {slots} position(s) but tasks need {needed}; "
            "the model will be infeasible."
        )
    elif slots > needed:
        notes.append(f"{slots - needed} agent slot(s) will stay unused.")

    return Formulation(
        title=p.name,
        objective_english=(
            f"{'Minimize total cost' if minimize else 'Maximize total score'} over the "
            f"{len(p.pairings)} allowed agent–task pairs."
        ),
        objective_latex=(r"\min" if minimize else r"\max") + r" \sum_{(a,t) \in P} v_{at}\, y_{at}",
        sets=[
            SetDef(symbol="A", name="Agents", members=agents),
            SetDef(symbol="T", name="Tasks", members=tasks),
            SetDef(
                symbol="P",
                name="Allowed pairs",
                members=[f"{x.agent}→{x.task}" for x in p.pairings],
            ),
        ],
        constraints=[
            ConstraintGroup(
                name="Agent capacity",
                english="Each agent takes no more than its capacity.",
                latex=r"\sum_{t:(a,t) \in P} y_{at} \le k_a \quad \forall a \in A",
                items=by_kind.get("agent_capacity", []),
            ),
            ConstraintGroup(
                name="Task requirement",
                english="Each task gets exactly the number of agents it needs.",
                latex=r"\sum_{a:(a,t) \in P} y_{at} = r_t \quad \forall t \in T",
                items=by_kind.get("task_requirement", []),
            ),
        ],
        domain_latex=r"0 \le y_{at} \le 1 \quad \forall (a,t) \in P",
        notes=notes,
    )


def describe_problem(problem: TransportationProblem | AssignmentProblem) -> Formulation:
    if isinstance(problem, TransportationProblem):
        return _transportation(problem)
    return _assignment(problem)

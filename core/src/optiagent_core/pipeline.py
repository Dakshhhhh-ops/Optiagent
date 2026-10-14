"""Deterministic end-to-end path: problem -> prechecks -> model -> solve -> verify -> interpret."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from optiagent_core.analysis import Sensitivity, analyze_sensitivity
from optiagent_core.builders import assign_var, build_model, flow_var
from optiagent_core.checks import Check, CheckReport, verify_solution
from optiagent_core.diagnose import Diagnosis, diagnose
from optiagent_core.explain import Insight, explain
from optiagent_core.model import LinearModel
from optiagent_core.prechecks import precheck
from optiagent_core.schema import AssignmentProblem, TransportationProblem
from optiagent_core.solver import SolveResult, SolveStatus, solve

ZERO_TOL = 1e-9


class Shipment(BaseModel):
    source: str
    destination: str
    quantity: float
    unit_cost: float
    cost: float


class SourceUsage(BaseModel):
    id: str
    supply: float
    shipped: float
    unused: float


class DestinationUsage(BaseModel):
    id: str
    demand: float
    received: float


class TransportationSolution(BaseModel):
    kind: Literal["transportation"] = "transportation"
    shipments: list[Shipment]
    sources: list[SourceUsage]
    destinations: list[DestinationUsage]


class Assignment(BaseModel):
    agent: str
    task: str
    value: float


class AssignmentSolution(BaseModel):
    kind: Literal["assignment"] = "assignment"
    assignments: list[Assignment]
    unassigned_agents: list[str]


class ModelStats(BaseModel):
    variables: int
    constraints: int
    nonzeros: int
    is_mip: bool


class SolveReport(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    prechecks: list[Check]
    stats: ModelStats
    model: LinearModel
    result: SolveResult
    verification: CheckReport
    solution: TransportationSolution | AssignmentSolution | None
    sensitivity: Sensitivity | None = None
    insights: list[Insight] = Field(default_factory=list)
    diagnosis: Diagnosis | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verified(self) -> bool:
        return self.verification.passed


def _interpret_transportation(
    problem: TransportationProblem, values: dict[str, float]
) -> TransportationSolution:
    shipments = []
    shipped: dict[str, float] = {s.id: 0.0 for s in problem.sources}
    received: dict[str, float] = {d.id: 0.0 for d in problem.destinations}
    for r in problem.routes:
        q = values.get(flow_var(r.source, r.destination), 0.0)
        if abs(q) <= ZERO_TOL:
            continue
        shipped[r.source] += q
        received[r.destination] += q
        shipments.append(
            Shipment(
                source=r.source,
                destination=r.destination,
                quantity=q,
                unit_cost=r.cost,
                cost=q * r.cost,
            )
        )
    return TransportationSolution(
        shipments=shipments,
        sources=[
            SourceUsage(
                id=s.id, supply=s.supply, shipped=shipped[s.id], unused=s.supply - shipped[s.id]
            )
            for s in problem.sources
        ],
        destinations=[
            DestinationUsage(id=d.id, demand=d.demand, received=received[d.id])
            for d in problem.destinations
        ],
    )


def _interpret_assignment(
    problem: AssignmentProblem, values: dict[str, float]
) -> AssignmentSolution:
    assignments = [
        Assignment(agent=p.agent, task=p.task, value=p.value)
        for p in problem.pairings
        if values.get(assign_var(p.agent, p.task), 0.0) > 0.5
    ]
    busy = {a.agent for a in assignments}
    return AssignmentSolution(
        assignments=assignments,
        unassigned_agents=[a.id for a in problem.agents if a.id not in busy],
    )


def interpret(
    problem: TransportationProblem | AssignmentProblem, values: dict[str, float]
) -> TransportationSolution | AssignmentSolution:
    if isinstance(problem, TransportationProblem):
        return _interpret_transportation(problem, values)
    return _interpret_assignment(problem, values)


def solve_problem(
    problem: TransportationProblem | AssignmentProblem, *, analyze: bool = False
) -> SolveReport:
    """Solve and verify. With `analyze`, also add sensitivity insights or an infeasibility
    diagnosis (extra solves, so it is off by default for internal callers)."""
    prechecks = precheck(problem)
    model = build_model(problem)
    result = solve(model)
    verification = verify_solution(model, result)
    solution = interpret(problem, result.values) if result.has_solution else None
    sensitivity: Sensitivity | None = None
    insights: list[Insight] = []
    diagnosis: Diagnosis | None = None
    if analyze and result.status == SolveStatus.OPTIMAL:
        sensitivity = analyze_sensitivity(model)
        insights = explain(
            sensitivity,
            minimize=problem.sense == "minimize",
            transport=isinstance(problem, TransportationProblem),
        )
    elif analyze and result.status == SolveStatus.INFEASIBLE:
        diagnosis = diagnose(model)
    return SolveReport(
        sensitivity=sensitivity,
        insights=insights,
        diagnosis=diagnosis,
        prechecks=prechecks,
        stats=ModelStats(
            variables=len(model.variables),
            constraints=len(model.constraints),
            nonzeros=sum(len(c.terms) for c in model.constraints),
            is_mip=model.is_mip,
        ),
        model=model,
        result=result,
        verification=verification,
        solution=solution,
    )

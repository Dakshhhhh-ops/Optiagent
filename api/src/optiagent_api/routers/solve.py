from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from optiagent_agent.audit import AuditReport, audit
from optiagent_agent.review import Review
from optiagent_agent.traceability import TraceabilityReport
from optiagent_api.auth import CurrentUser
from optiagent_api.routers.datasets import StoreDep
from optiagent_api.tracing import trace_on_server
from optiagent_core.examples import Example, list_examples
from optiagent_core.formulation import Formulation, describe_problem
from optiagent_core.ingest import AssignmentMapping, TransportationMapping
from optiagent_core.pipeline import SolveReport, solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem

router = APIRouter(prefix="/api/v1", tags=["solve"])


# Plain `def` so FastAPI runs the CPU-bound solve in its threadpool.
@router.post("/solve", response_model=SolveReport)
def solve(
    problem: Annotated[TransportationProblem | AssignmentProblem, Body(discriminator="kind")],
) -> SolveReport:
    return solve_problem(problem, analyze=True)


@router.get("/examples", response_model=list[Example])
def examples() -> list[Example]:
    return list_examples()


@router.get("/examples/{example_id}", response_model=Example)
def example(example_id: str) -> Example:
    for e in list_examples():
        if e.id == example_id:
            return e
    raise HTTPException(status_code=404, detail=f"unknown example {example_id!r}")


@router.post("/formulation", response_model=Formulation)
def formulation(
    problem: Annotated[TransportationProblem | AssignmentProblem, Body(discriminator="kind")],
) -> Formulation:
    return describe_problem(problem)


class AuditRequest(BaseModel):
    problem: TransportationProblem | AssignmentProblem = Field(discriminator="kind")
    text: str | None = Field(default=None, max_length=20_000)


@router.post("/audit", response_model=AuditReport)
def audit_endpoint(request: AuditRequest) -> AuditReport:
    return audit(request.problem, request.text)


class TraceabilityRequest(BaseModel):
    problem: TransportationProblem | AssignmentProblem = Field(discriminator="kind")
    text: str | None = Field(default=None, max_length=20_000)
    requirements: list[Annotated[str, Field(max_length=2_000)]] = Field(
        default_factory=list, max_length=50
    )
    review: Review | None = None
    dataset_id: str | None = None
    mapping: TransportationMapping | AssignmentMapping | None = Field(
        default=None, discriminator="kind"
    )
    """With dataset_id: how the problem was read from the upload (re-checked on the server)."""


@router.post("/traceability", response_model=TraceabilityReport)
def traceability_endpoint(
    request: TraceabilityRequest, datasets: StoreDep, user: CurrentUser
) -> TraceabilityReport:
    """Deterministic requirement traceability and provenance (no AI call)."""
    return trace_on_server(
        request.problem,
        request.text,
        dataset_id=request.dataset_id,
        mapping=request.mapping,
        requirements=request.requirements,
        review=request.review,
        datasets=datasets,
        user=user,
    )

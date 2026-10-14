from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from optiagent_agent.audit import AuditReport, audit
from optiagent_core.examples import Example, list_examples
from optiagent_core.formulation import Formulation, describe_problem
from optiagent_core.pipeline import SolveReport, solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem

router = APIRouter(prefix="/api/v1", tags=["solve"])


# Plain `def` so FastAPI runs the CPU-bound solve in its threadpool.
@router.post("/solve", response_model=SolveReport)
def solve(
    problem: Annotated[TransportationProblem | AssignmentProblem, Body(discriminator="kind")],
) -> SolveReport:
    return solve_problem(problem)


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

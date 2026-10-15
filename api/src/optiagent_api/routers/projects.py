from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from optiagent_agent.review import Review
from optiagent_agent.traceability import TraceabilityReport, TraceRow, trace
from optiagent_api.auth import CurrentUser
from optiagent_api.datasets import DatasetStore
from optiagent_api.db import get_engine
from optiagent_api.projects import Project, ProjectStore, ProjectSummary
from optiagent_api.routers.datasets import StoreDep
from optiagent_api.settings import get_settings
from optiagent_core.ingest import AssignmentMapping, TransportationMapping, load_problem
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def get_projects() -> ProjectStore:
    return ProjectStore(get_engine(get_settings().database_url))


ProjectsDep = Annotated[ProjectStore, Depends(get_projects)]


class CreateProject(BaseModel):
    problem: TransportationProblem | AssignmentProblem = Field(discriminator="kind")
    source: Literal["ai", "manual"]
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    dataset_id: str | None = None
    mapping: TransportationMapping | AssignmentMapping | None = Field(
        default=None, discriminator="kind"
    )
    """How the problem was read from the dataset. Checked on the server before it is trusted."""
    requirements: list[Annotated[str, Field(max_length=2_000)]] = Field(
        default_factory=list, max_length=50
    )
    review: Review | None = None
    """An AI requirement review, if one was run. It can only flag gaps, never verify."""


def _traceability(
    request: CreateProject, datasets: DatasetStore, user: str | None
) -> TraceabilityReport:
    """Trace on the server, from data the server holds wherever possible."""

    def run(mapping: TransportationMapping | AssignmentMapping | None) -> TraceabilityReport:
        return trace(
            request.problem,
            request.description,
            mapping=mapping,
            requirements=request.requirements,
            review=request.review,
        )

    if not (request.dataset_id and request.mapping is not None):
        return run(None)
    try:
        tables = datasets.tables(request.dataset_id, user)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {request.dataset_id!r}") from None
    if load_problem(tables, request.mapping).problem == request.problem:
        return run(request.mapping)
    report = run(None)
    mismatch = TraceRow(
        requirement="uploaded data",
        interpretation="The problem differs from what the mapping reads from the uploaded files.",
        method="file_data",
        status="unresolved",
        note="Values were changed after loading, or the mapping is not the one used.",
    )
    report.requirements.insert(0, mismatch)
    return report


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _default_name(request: CreateProject) -> str:
    if request.description and request.description.strip():
        words = request.description.split()
        return " ".join(words[:8]) + ("…" if len(words) > 8 else "")
    return request.problem.name


@router.post("", response_model=Project, status_code=201)
def create(
    request: CreateProject, projects: ProjectsDep, datasets: StoreDep, user: CurrentUser
) -> Project:
    # Solve and trace on the server: a saved project never stores a result computed elsewhere.
    traceability = _traceability(request, datasets, user)
    report = solve_problem(request.problem, analyze=True)
    return projects.create(
        name=request.name or _default_name(request),
        source=request.source,
        problem=request.problem,
        report=report,
        traceability=traceability,
        description=request.description,
        dataset_id=request.dataset_id,
        owner_id=user,
    )


@router.get("", response_model=list[ProjectSummary])
def list_projects(projects: ProjectsDep, user: CurrentUser) -> list[ProjectSummary]:
    return projects.list(user)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, projects: ProjectsDep, user: CurrentUser) -> Project:
    project = projects.get(project_id, user)
    if project is None:
        raise HTTPException(404, f"unknown project {project_id!r}")
    return project


@router.patch("/{project_id}", response_model=Project)
def rename(project_id: str, request: Rename, projects: ProjectsDep, user: CurrentUser) -> Project:
    project = projects.rename(project_id, request.name.strip(), user)
    if project is None:
        raise HTTPException(404, f"unknown project {project_id!r}")
    return project


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, projects: ProjectsDep, user: CurrentUser) -> Response:
    if not projects.delete(project_id, user):
        raise HTTPException(404, f"unknown project {project_id!r}")
    return Response(status_code=204)

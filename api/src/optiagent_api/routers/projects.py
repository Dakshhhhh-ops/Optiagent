from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from optiagent_api.projects import Project, ProjectStore, ProjectSummary
from optiagent_api.settings import get_settings
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def get_projects() -> ProjectStore:
    return ProjectStore(get_settings().database_path)


ProjectsDep = Annotated[ProjectStore, Depends(get_projects)]


class CreateProject(BaseModel):
    problem: TransportationProblem | AssignmentProblem = Field(discriminator="kind")
    source: Literal["ai", "manual"]
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    dataset_id: str | None = None


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _default_name(request: CreateProject) -> str:
    if request.description and request.description.strip():
        words = request.description.split()
        return " ".join(words[:8]) + ("…" if len(words) > 8 else "")
    return request.problem.name


@router.post("", response_model=Project, status_code=201)
def create(request: CreateProject, projects: ProjectsDep) -> Project:
    # Solve on the server: a saved project never stores a result computed elsewhere.
    report = solve_problem(request.problem, analyze=True)
    return projects.create(
        name=request.name or _default_name(request),
        source=request.source,
        problem=request.problem,
        report=report,
        description=request.description,
        dataset_id=request.dataset_id,
    )


@router.get("", response_model=list[ProjectSummary])
def list_projects(projects: ProjectsDep) -> list[ProjectSummary]:
    return projects.list()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, projects: ProjectsDep) -> Project:
    project = projects.get(project_id)
    if project is None:
        raise HTTPException(404, f"unknown project {project_id!r}")
    return project


@router.patch("/{project_id}", response_model=Project)
def rename(project_id: str, request: Rename, projects: ProjectsDep) -> Project:
    project = projects.rename(project_id, request.name.strip())
    if project is None:
        raise HTTPException(404, f"unknown project {project_id!r}")
    return project


@router.delete("/{project_id}", status_code=204)
def delete(project_id: str, projects: ProjectsDep) -> Response:
    if not projects.delete(project_id):
        raise HTTPException(404, f"unknown project {project_id!r}")
    return Response(status_code=204)

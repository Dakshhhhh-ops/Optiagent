"""LLM endpoints: analyze a description, then extract a problem from text or uploaded data."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from optiagent_agent.audit import AuditReport, audit
from optiagent_agent.grounding import Ungrounded
from optiagent_agent.llm import LLM, LLMError, Trace
from optiagent_agent.pipeline import (
    Analysis,
    Answer,
    analyze,
    extract_from_data,
    extract_from_text,
    with_answers,
)
from optiagent_agent.providers import make_llm
from optiagent_agent.review import Review, review_requirements
from optiagent_api.datasets import DatasetStore
from optiagent_api.routers.datasets import StoreDep
from optiagent_api.settings import get_settings
from optiagent_core.formulation import Formulation, describe_problem
from optiagent_core.ingest import (
    AssignmentMapping,
    DataIssue,
    Table,
    TransportationMapping,
    profile_table,
)
from optiagent_core.schema import AssignmentProblem, TransportationProblem

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def get_llm() -> LLM:
    return make_llm(get_settings().llm_config())


LLMDep = Annotated[LLM, Depends(get_llm)]


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    dataset_id: str | None = None


class AnalyzeResponse(BaseModel):
    analysis: Analysis
    trace: Trace


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    kind: Literal["transportation", "assignment"]
    answers: list[Answer] = Field(default_factory=list)
    dataset_id: str | None = None


class ExtractResponse(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    problem: TransportationProblem | AssignmentProblem | None
    mapping: TransportationMapping | AssignmentMapping | None = None
    formulation: Formulation | None = None
    ungrounded: list[Ungrounded] = Field(default_factory=list)
    issues: list[DataIssue] = Field(default_factory=list)
    audit: AuditReport | None = None
    trace: Trace


def _tables(store: DatasetStore, dataset_id: str) -> list[Table]:
    try:
        return store.tables(dataset_id)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {dataset_id!r}") from None


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(
    request: AnalyzeRequest, llm: LLMDep, store: StoreDep
) -> AnalyzeResponse:
    profiles = (
        [profile_table(t, preview_rows=3) for t in _tables(store, request.dataset_id)]
        if request.dataset_id
        else None
    )
    try:
        analysis, trace = await analyze(llm, request.text, profiles)
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from None
    return AnalyzeResponse(analysis=analysis, trace=trace)


@router.post("/extract", response_model=ExtractResponse)
async def extract_endpoint(
    request: ExtractRequest, llm: LLMDep, store: StoreDep
) -> ExtractResponse:
    text = with_answers(request.text, request.answers)
    try:
        if request.dataset_id:
            tables = _tables(store, request.dataset_id)
            profiles = [profile_table(t, preview_rows=3) for t in tables]
            data = await extract_from_data(llm, text, request.kind, tables, profiles)
            response = ExtractResponse(
                problem=data.problem, mapping=data.mapping, issues=data.issues, trace=data.trace
            )
        else:
            extraction = await extract_from_text(llm, text, request.kind)
            response = ExtractResponse(
                problem=extraction.problem,
                ungrounded=extraction.ungrounded,
                trace=extraction.trace,
            )
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from None
    if response.problem is not None:
        response.formulation = describe_problem(response.problem)
        response.audit = audit(response.problem, text)
    return response


class ReviewRequest(BaseModel):
    requirements: list[str] = Field(min_length=1, max_length=50)
    problem: TransportationProblem | AssignmentProblem = Field(discriminator="kind")


class ReviewResponse(BaseModel):
    review: Review
    trace: Trace


@router.post("/review", response_model=ReviewResponse)
async def review_endpoint(request: ReviewRequest, llm: LLMDep) -> ReviewResponse:
    try:
        review, trace = await review_requirements(
            llm, request.requirements, describe_problem(request.problem)
        )
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from None
    return ReviewResponse(review=review, trace=trace)

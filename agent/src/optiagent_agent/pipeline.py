"""The LLM steps: analyze -> (clarify) -> extract from text, or propose a mapping for data.

The LLM only ever produces typed structures. Numbers from files are loaded by code; numbers
from text are checked against the text (grounding) before anything is solved.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from optiagent_agent import prompts
from optiagent_agent.grounding import Ungrounded, ungrounded_values
from optiagent_agent.llm import LLM, Trace, structured
from optiagent_core.ingest import (
    AssignmentMapping,
    DataIssue,
    Table,
    TableProfile,
    TransportationMapping,
    load_problem,
)
from optiagent_core.schema import AssignmentProblem, TransportationProblem

Kind = Literal["transportation", "assignment"]
Problem = TransportationProblem | AssignmentProblem


class Analysis(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    kind: Literal["transportation", "assignment", "unsupported"] = Field(
        description="Which supported problem type this is, or unsupported."
    )
    summary: str = Field(description="One plain sentence restating the problem.")
    requirements: list[str] = Field(
        description="Every objective and constraint the user states, one short item each."
    )
    questions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Only required information that is missing. Empty if nothing is missing.",
    )


class Answer(BaseModel):
    question: str
    answer: str


class TextExtraction(BaseModel):
    problem: Problem | None
    ungrounded: list[Ungrounded]
    trace: Trace


class DataExtraction(BaseModel):
    mapping: TransportationMapping | AssignmentMapping | None
    problem: Problem | None
    issues: list[DataIssue]
    trace: Trace


def with_answers(text: str, answers: list[Answer]) -> str:
    if not answers:
        return text
    extra = "\n".join(f"Q: {a.question}\nA: {a.answer}" for a in answers)
    return f"{text}\n\nAdditional information from the user:\n{extra}"


async def analyze(
    llm: LLM, text: str, tables: list[TableProfile] | None = None, trace: Trace | None = None
) -> tuple[Analysis, Trace]:
    trace = trace or Trace()
    user = text
    if tables:
        user += "\n\nUploaded data tables:\n" + prompts.describe_tables(tables)
    analysis = await structured(
        llm, step="analyze", system=prompts.ANALYZE, user=user, output=Analysis, trace=trace
    )
    return analysis, trace


async def extract_from_text(
    llm: LLM, text: str, kind: Kind, trace: Trace | None = None, *, verify: bool = True
) -> TextExtraction:
    """Extract a full problem from prose. Values not found in the text trigger a retry.

    `verify=False` is the no-verification baseline: one attempt, no grounding feedback.
    """
    trace = trace or Trace()
    attempts = 3 if verify else 1

    def validate(problem: Problem) -> list[str]:
        return [
            f"{u.field} = {u.value:g} does not appear in the problem text. "
            "Use only numbers stated in the text."
            for u in ungrounded_values(problem, text)
        ]

    problem: Problem
    if kind == "transportation":
        problem = await structured(
            llm,
            step="extract_transportation",
            system=prompts.EXTRACT_TRANSPORTATION,
            user=text,
            output=TransportationProblem,
            trace=trace,
            validate=validate if verify else None,
            max_attempts=attempts,
        )
    else:
        problem = await structured(
            llm,
            step="extract_assignment",
            system=prompts.EXTRACT_ASSIGNMENT,
            user=text,
            output=AssignmentProblem,
            trace=trace,
            validate=validate if verify else None,
            max_attempts=attempts,
        )
    return TextExtraction(problem=problem, ungrounded=ungrounded_values(problem, text), trace=trace)


def _mapping_errors(issues: list[DataIssue]) -> list[str]:
    """Errors the mapping can fix (wrong table/column), as opposed to bad cells in the file."""
    return [i.message for i in issues if i.severity == "error" and i.row is None]


async def extract_from_data(
    llm: LLM,
    text: str,
    kind: Kind,
    tables: list[Table],
    profiles: list[TableProfile],
    trace: Trace | None = None,
) -> DataExtraction:
    """Ask the LLM where the values live; code loads them."""
    trace = trace or Trace()
    user = f"{text}\n\nUploaded data tables:\n{prompts.describe_tables(profiles)}"

    def validate(mapping: TransportationMapping | AssignmentMapping) -> list[str]:
        return _mapping_errors(load_problem(tables, mapping).issues)

    mapping: TransportationMapping | AssignmentMapping
    if kind == "transportation":
        mapping = await structured(
            llm,
            step="map_transportation",
            system=prompts.MAPPING,
            user=user,
            output=TransportationMapping,
            trace=trace,
            validate=validate,
        )
    else:
        mapping = await structured(
            llm,
            step="map_assignment",
            system=prompts.MAPPING,
            user=user,
            output=AssignmentMapping,
            trace=trace,
            validate=validate,
        )
    loaded = load_problem(tables, mapping)
    return DataExtraction(
        mapping=mapping, problem=loaded.problem, issues=loaded.issues, trace=trace
    )

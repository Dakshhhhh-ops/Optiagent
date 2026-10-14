"""LLM round-trip review: does the rendered formulation cover each stated requirement?

The formulation shown to the model is the deterministic plain-English rendering, not the
LLM's own extraction, so this is an independent second reading. It is advisory: its findings
are warnings, never hard errors.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from optiagent_agent.llm import LLM, Trace, structured
from optiagent_core.formulation import Formulation

REVIEW = """You check an optimization model against the user's requirements.

You get the user's numbered requirements and the model, written in plain English.
For EACH requirement, in order, decide:
- covered: the model enforces it (or it is the objective and the objective matches).
- missing: the model has nothing that enforces it.
- contradicted: the model enforces something different (wrong direction, wrong number,
  wrong items, minimize instead of maximize, ...).
- not_applicable: it is background information, not a rule the model must enforce.
In "where", name the part of the model you used (e.g. "Objective", "Supply", "Demand").
In "unexplained", list model rules that no requirement asks for (empty if none).
Judge only what is written. Do not assume."""


class RequirementCheck(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    requirement: str
    status: Literal["covered", "missing", "contradicted", "not_applicable"]
    where: str = ""
    reason: str = ""


class Review(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    checks: list[RequirementCheck]
    unexplained: list[str] = Field(default_factory=list)


def render(f: Formulation, max_items: int = 30) -> str:
    lines = [f"Objective: {f.objective_english}"]
    for c in f.constraints:
        lines.append(f"{c.name}: {c.english}")
        lines += [f"  - {item}" for item in c.items[:max_items]]
        if len(c.items) > max_items:
            lines.append(f"  - ... and {len(c.items) - max_items} more")
    lines += [f"Note: {n}" for n in f.notes]
    return "\n".join(lines)


async def review_requirements(
    llm: LLM, requirements: list[str], formulation: Formulation, trace: Trace | None = None
) -> tuple[Review, Trace]:
    trace = trace or Trace()
    numbered = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(requirements))
    user = f"Requirements:\n{numbered}\n\nModel:\n{render(formulation)}"

    def validate(review: Review) -> list[str]:
        if len(review.checks) != len(requirements):
            return [f"Return exactly {len(requirements)} checks, one per requirement, in order."]
        return []

    review = await structured(
        llm, step="review", system=REVIEW, user=user, output=Review, trace=trace, validate=validate
    )
    # Keep the user's exact wording, whatever the model echoed back.
    for check, requirement in zip(review.checks, requirements, strict=False):
        check.requirement = requirement
    return review, trace

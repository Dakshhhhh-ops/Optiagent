"""Typed problem specifications.

These are the only structures the LLM layer is allowed to produce. Everything downstream
(model building, solving, checking) is deterministic code operating on them.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonNegative = Annotated[float, Field(ge=0)]

# Size limits: enough for real planning problems, small enough that one request cannot
# tie up the solver (and that an LLM cannot produce an absurd model).
MAX_ENTITIES = 5_000
MAX_PAIRS = 100_000
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_unique(kind: str, ids: list[str]) -> None:
    dupes = sorted(i for i, n in Counter(ids).items() if n > 1)
    if dupes:
        raise ValueError(f"duplicate {kind} ids: {', '.join(dupes)}")


# --------------------------------------------------------------------------- transportation


class Source(_Strict):
    id: Identifier
    supply: NonNegative


class Destination(_Strict):
    id: Identifier
    demand: NonNegative


class Route(_Strict):
    source: Identifier
    destination: Identifier
    cost: float
    capacity: NonNegative | None = None
    """Upper bound on the quantity shipped on this route. None means unbounded."""


class TransportationProblem(_Strict):
    """Ship goods from sources to destinations at minimum (or maximum) total cost.

    Routes that are not listed are not allowed.
    """

    kind: Literal["transportation"] = "transportation"
    name: str = "Transportation problem"
    sense: Literal["minimize", "maximize"] = "minimize"
    sources: list[Source] = Field(min_length=1, max_length=MAX_ENTITIES)
    destinations: list[Destination] = Field(min_length=1, max_length=MAX_ENTITIES)
    routes: list[Route] = Field(min_length=1, max_length=MAX_PAIRS)
    demand_constraint: Literal["equal", "at_least"] = "equal"
    """Whether each destination must receive exactly its demand or at least its demand."""

    @model_validator(mode="after")
    def _check_references(self) -> TransportationProblem:
        _check_unique("source", [s.id for s in self.sources])
        _check_unique("destination", [d.id for d in self.destinations])
        source_ids = {s.id for s in self.sources}
        destination_ids = {d.id for d in self.destinations}
        for r in self.routes:
            if r.source not in source_ids:
                raise ValueError(f"route references unknown source {r.source!r}")
            if r.destination not in destination_ids:
                raise ValueError(f"route references unknown destination {r.destination!r}")
        _check_unique("route", [f"{r.source}->{r.destination}" for r in self.routes])
        return self


# --------------------------------------------------------------------------- assignment


class Agent(_Strict):
    id: Identifier
    capacity: Annotated[int, Field(ge=0)] = 1
    """Maximum number of tasks this agent can take."""


class Task(_Strict):
    id: Identifier
    required: Annotated[int, Field(ge=0)] = 1
    """Exact number of agents this task needs."""


class Pairing(_Strict):
    agent: Identifier
    task: Identifier
    value: float
    """Cost when minimizing, score/preference when maximizing."""


class AssignmentProblem(_Strict):
    """Assign agents to tasks. Pairings that are not listed are not allowed.

    Integer capacities and requirements keep the constraint matrix totally unimodular,
    so the LP relaxation already has an integral optimum and LP duals stay meaningful.
    """

    kind: Literal["assignment"] = "assignment"
    name: str = "Assignment problem"
    sense: Literal["minimize", "maximize"] = "minimize"
    agents: list[Agent] = Field(min_length=1, max_length=MAX_ENTITIES)
    tasks: list[Task] = Field(min_length=1, max_length=MAX_ENTITIES)
    pairings: list[Pairing] = Field(min_length=1, max_length=MAX_PAIRS)

    @model_validator(mode="after")
    def _check_references(self) -> AssignmentProblem:
        _check_unique("agent", [a.id for a in self.agents])
        _check_unique("task", [t.id for t in self.tasks])
        agent_ids = {a.id for a in self.agents}
        task_ids = {t.id for t in self.tasks}
        for p in self.pairings:
            if p.agent not in agent_ids:
                raise ValueError(f"pairing references unknown agent {p.agent!r}")
            if p.task not in task_ids:
                raise ValueError(f"pairing references unknown task {p.task!r}")
        _check_unique("pairing", [f"{p.agent}->{p.task}" for p in self.pairings])
        return self


ProblemSpec = Annotated[TransportationProblem | AssignmentProblem, Field(discriminator="kind")]

"""Solver-independent linear model.

Builders turn a typed problem into a LinearModel; the solver, the checks, the audit and
the UI all read this one structure. Every variable and constraint carries an Origin that
links it back to the element of the problem it came from.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Sense = Literal["<=", ">=", "=="]


class Origin(BaseModel):
    """Where a model element came from, e.g. Origin(kind="supply", keys=("Plant A",))."""

    kind: str
    keys: tuple[str, ...] = ()


class Variable(BaseModel):
    name: str
    lb: float = 0.0
    ub: float | None = None
    integer: bool = False
    expect_integral: bool = False
    """Solved as continuous, but the structure guarantees an integral optimum (checked)."""
    objective: float = 0.0
    origin: Origin


class Constraint(BaseModel):
    name: str
    terms: dict[str, float]
    sense: Sense
    rhs: float
    origin: Origin
    description: str = ""


class LinearModel(BaseModel):
    name: str
    sense: Literal["minimize", "maximize"]
    variables: list[Variable] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)

    def variable(self, name: str) -> Variable:
        for v in self.variables:
            if v.name == name:
                return v
        raise KeyError(name)

    def objective_value(self, values: dict[str, float]) -> float:
        return sum(v.objective * values.get(v.name, 0.0) for v in self.variables)

    @staticmethod
    def activity(constraint: Constraint, values: dict[str, float]) -> float:
        return sum(coef * values.get(name, 0.0) for name, coef in constraint.terms.items())

    @property
    def is_mip(self) -> bool:
        return any(v.integer for v in self.variables)

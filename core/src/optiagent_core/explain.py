"""Deterministic business-language insights from the sensitivity analysis.

Every number in an insight comes from the analysis object it cites, so explanations can be
traced back to solver output. Marginal effects use the exact one-unit re-solves, not raw duals,
so they stay correct when the problem is degenerate.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from optiagent_core.analysis import ConstraintInsight, Effect, Sensitivity, VariableInsight

Kind = Literal["alternative_optimum", "binding", "slack", "unused_option", "cost_range", "limit"]


class Insight(BaseModel):
    kind: Kind
    title: str
    text: str
    impact: float
    """Absolute objective change per unit, used for ranking."""
    source: str
    """Name of the constraint or variable this insight is computed from."""


def _n(x: float) -> str:
    return f"{x:,.6g}"


def _effect(delta: float | None, effect: Effect | None, minimize: bool, objective: str) -> str:
    if effect == "not_applicable":
        return "is not possible (it is already zero)"
    if effect == "solver_failed":
        return "could not be evaluated (the re-solve did not finish)"
    if delta is None:
        return "would make the plan infeasible"
    if abs(delta) < 1e-9:
        return f"would not change the {objective}"
    better = (delta < 0) if minimize else (delta > 0)
    return f"would {'improve' if better else 'worsen'} the {objective} by {_n(abs(delta))}"


def _constraint_insight(c: ConstraintInsight, transport: bool, minimize: bool) -> Insight | None:
    objective = "total cost" if minimize else "total score"
    who = c.keys[0] if c.keys else c.name
    labels = {
        "supply": ("supply at", "unit of supply", "units"),
        "demand": ("demand at", "unit of demand", "units"),
        "agent_capacity": ("capacity of", "task for", "task(s)"),
        "task_requirement": ("staffing of", "agent on", "agent(s)"),
    }
    if c.kind not in labels:
        return None
    what, one, unit = labels[c.kind]

    if not c.binding:
        return Insight(
            kind="slack",
            title=f"{who} has spare capacity",
            text=(
                f"{who} uses {_n(c.activity)} of {_n(c.rhs)} {unit}; {_n(c.slack)} stay unused, "
                f"so more {what.split()[0]} there is worth nothing right now."
            ),
            impact=0.0,
            source=c.name,
        )

    up, down = c.change_if_increased, c.change_if_decreased
    if c.kind in ("agent_capacity", "task_requirement"):
        more = f"One more {one} {who} {_effect(up, c.effect_if_increased, minimize, objective)}"
        less = f"one fewer {_effect(down, c.effect_if_decreased, minimize, objective)}"
    else:
        more = f"One more {one} {who if c.kind == 'supply' else 'at ' + who} {_effect(up, c.effect_if_increased, minimize, objective)}"
        less = f"one less {_effect(down, c.effect_if_decreased, minimize, objective)}"
    impact = max(abs(up or 0), abs(down or 0))
    asymmetric = up is not None and down is not None and abs(abs(up) - abs(down)) > 1e-9
    text = f"{more}; {less}."
    if asymmetric:
        text += " The effect differs by direction because the optimal plan sits on a corner."
    return Insight(
        kind="binding",
        title=f"The {what} {who} limits the plan",
        text=text,
        impact=impact,
        source=c.name,
    )


def _variable_insight(v: VariableInsight, minimize: bool, transport: bool) -> Insight | None:
    if len(v.keys) != 2:
        return None
    frm, to = v.keys
    objective = "total cost" if minimize else "total score"
    if v.status == "at_lower" and v.value <= 1e-9 and abs(v.reduced_cost) > 1e-9:
        if minimize and v.cost - abs(v.reduced_cost) < 0:
            text = (
                f"{frm} → {to} is not used, and would stay unused even if it cost nothing "
                f"(the current plan is better by {_n(abs(v.reduced_cost))} per unit)."
            )
        elif minimize:
            text = (
                f"{frm} → {to} is not used. It becomes worth using only if its cost falls by more "
                f"than {_n(abs(v.reduced_cost))} (from {_n(v.cost)} to below {_n(v.cost - abs(v.reduced_cost))})."
            )
        else:
            text = (
                f"{frm} → {to} is not used. It becomes worth using only if its value rises by more "
                f"than {_n(abs(v.reduced_cost))} (from {_n(v.cost)} to above {_n(v.cost + abs(v.reduced_cost))})."
            )
        return Insight(kind="unused_option", title=f"{frm} → {to} is unused", text=text,
                       impact=abs(v.reduced_cost), source=v.name)  # fmt: skip
    if v.alternative_use is not None:
        return Insight(
            kind="alternative_optimum",
            title=f"Another equally good plan uses {frm} → {to}",
            text=(
                f"{frm} → {to} is unused in this plan, but a different plan with exactly the same "
                f"{objective} can use it (up to {_n(v.alternative_use)}). The optimum is not unique; "
                "choose between such plans on criteria the model does not include."
            ),
            impact=0.0,
            source=v.name,
        )
    if v.status == "at_upper" and v.kind == "route" and abs(v.reduced_cost) > 1e-9:
        delta = v.change_if_limit_raised
        effect = (
            _effect(delta, "changed", minimize, objective)
            if delta is not None
            else f"would change the {objective} by about {_n(abs(v.reduced_cost))} (local estimate)"
        )
        return Insight(
            kind="limit",
            title=f"The {frm} → {to} route limit is binding",
            text=f"{frm} → {to} is used at its limit of {_n(v.value)}. Raising the limit by one unit {effect}.",
            impact=abs(delta) if delta is not None else abs(v.reduced_cost),
            source=v.name,
        )
    if v.value > 1e-9 and (v.cost_from is not None or v.cost_to is not None):
        lo = _n(v.cost_from) if v.cost_from is not None else "any lower value"
        hi = _n(v.cost_to) if v.cost_to is not None else "any higher value"
        return Insight(
            kind="cost_range",
            title=f"{frm} → {to} {'cost' if transport else 'value'} range",
            text=(
                f"The plan stays optimal while the {frm} → {to} {'cost' if transport else 'value'} "
                f"stays between {lo} and {hi} (now {_n(v.cost)}), all other data unchanged. "
                "This is a local range from the solver, not a forecast."
            ),
            impact=0.0,
            source=v.name,
        )
    return None


def explain(sensitivity: Sensitivity, minimize: bool, transport: bool) -> list[Insight]:
    if not sensitivity.available:
        return []
    insights = [
        i
        for c in sensitivity.constraints
        if (i := _constraint_insight(c, transport, minimize)) is not None
    ]
    insights += [
        i
        for v in sensitivity.variables
        if (i := _variable_insight(v, minimize, transport)) is not None
    ]
    order = {
        "alternative_optimum": 0,
        "binding": 1,
        "limit": 2,
        "unused_option": 3,
        "slack": 4,
        "cost_range": 5,
    }
    return sorted(insights, key=lambda i: (order[i.kind], -i.impact))

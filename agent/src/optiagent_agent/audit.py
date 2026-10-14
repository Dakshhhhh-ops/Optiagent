"""Formulation audit: catch modelling errors by checking the model against the user's text.

Deterministic checks (no LLM):
  - text cross-check: pair values, forbidden pairs, route limits and quantities read from the
    text must match the model, and no stated value may be missing
  - unused numbers: numbers in the text that the model never uses
  - wording: maximize/minimize and "at least" demand must match the model
  - structure: every entity takes part in at least one allowed pair
  - sanity: a greedy feasible plan is accepted and is no better than the optimum; doubling
    every cost doubles the objective

An optional LLM check compares the user's stated requirements with the rendered formulation.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from optiagent_agent.textfacts import Num, extract_facts
from optiagent_core.builders import assign_var, build_model, flow_var
from optiagent_core.model import LinearModel
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem
from optiagent_core.solver import SolveStatus

Problem = TransportationProblem | AssignmentProblem
Severity = Literal["error", "warning", "info"]


class Finding(BaseModel):
    check: str
    severity: Severity
    message: str
    evidence: str | None = None


class AuditReport(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    findings: list[Finding] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def add(
        self, check: str, severity: Severity, message: str, evidence: str | None = None
    ) -> None:
        self.findings.append(
            Finding(check=check, severity=severity, message=message, evidence=evidence)
        )


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def _pairs(problem: Problem) -> dict[tuple[str, str], float]:
    if isinstance(problem, TransportationProblem):
        return {(r.source, r.destination): r.cost for r in problem.routes}
    return {(p.agent, p.task): p.value for p in problem.pairings}


def _entity_values(problem: Problem) -> dict[tuple[str, str], tuple[str, float]]:
    """(role, id) -> (what it means, value)."""
    if isinstance(problem, TransportationProblem):
        return {
            **{("from", s.id): ("supply", s.supply) for s in problem.sources},
            **{("to", d.id): ("demand", d.demand) for d in problem.destinations},
        }
    return {
        **{("from", a.id): ("capacity", float(a.capacity)) for a in problem.agents},
        **{("to", t.id): ("agents needed", float(t.required)) for t in problem.tasks},
    }


# --------------------------------------------------------------------------- text checks


def _text_checks(problem: Problem, text: str, report: AuditReport) -> None:
    report.checks_run += ["text_cross_check", "unused_numbers", "wording"]
    facts = extract_facts(text, problem)
    pairs = _pairs(problem)
    pair_name = "route" if isinstance(problem, TransportationProblem) else "pair"

    for fact in facts.pairs:
        key = (fact.frm, fact.to)
        if fact.value is None:
            if key in pairs:
                report.add(
                    "text_cross_check", "error",
                    f"The text says {fact.frm} → {fact.to} is not allowed, but the model includes it.",
                    fact.snippet,
                )  # fmt: skip
        elif key not in pairs:
            report.add(
                "text_cross_check", "error",
                f"The text gives {fact.frm} → {fact.to} = {fact.value:g}, but the model has no such {pair_name}.",
                fact.snippet,
            )  # fmt: skip
        elif not _close(pairs[key], fact.value):
            report.add(
                "text_cross_check", "error",
                f"{fact.frm} → {fact.to} is {fact.value:g} in the text but {pairs[key]:g} in the model.",
                fact.snippet,
            )  # fmt: skip

    entities = _entity_values(problem)
    for efact in facts.entities:
        if (efact.role, efact.id) not in entities:
            continue
        meaning, value = entities[(efact.role, efact.id)]
        if not _close(value, efact.value):
            report.add(
                "text_cross_check", "error",
                f"The {meaning} of {efact.id} is {efact.value:g} in the text but {value:g} in the model.",
                efact.snippet,
            )  # fmt: skip

    stated_ids = {(f.role, f.id) for f in facts.entities}
    if isinstance(problem, AssignmentProblem):
        for role in facts.default_one:
            for (r, ident), (meaning, value) in entities.items():
                if r == role and (r, ident) not in stated_ids and not _close(value, 1):
                    report.add(
                        "text_cross_check", "error",
                        f"The text implies {ident} has {meaning} 1, but the model uses {value:g}.",
                    )  # fmt: skip

    if isinstance(problem, TransportationProblem):
        caps = {
            (r.source, r.destination): r.capacity for r in problem.routes if r.capacity is not None
        }
        stated = {(f.frm, f.to): f for f in facts.limits}
        for key, fact in stated.items():
            if key not in caps:
                report.add(
                    "route_limit", "error",
                    f"The text limits {key[0]} → {key[1]} to {fact.value:g}, but the model has no limit there.",
                    fact.snippet,
                )  # fmt: skip
            elif fact.value is not None and not _close(caps[key], fact.value):
                report.add(
                    "route_limit", "error",
                    f"The limit on {key[0]} → {key[1]} is {fact.value:g} in the text but {caps[key]:g} in the model.",
                    fact.snippet,
                )  # fmt: skip
        for key, cap in caps.items():
            if key not in stated:
                report.add(
                    "route_limit", "warning",
                    f"The model limits {key[0]} → {key[1]} to {cap:g}, but the text does not state that limit.",
                )  # fmt: skip

        if facts.says_at_least and problem.demand_constraint == "equal":
            report.add(
                "wording", "warning",
                'The text says "at least", but each destination must receive exactly its demand.',
            )  # fmt: skip
        if not facts.says_at_least and problem.demand_constraint == "at_least":
            report.add(
                "wording", "warning",
                'The model lets destinations receive more than their demand, but the text never says "at least".',
            )  # fmt: skip

    if facts.wants_max and not facts.wants_min and problem.sense == "minimize":
        report.add("wording", "error", "The text asks to maximize, but the model minimizes.")
    if facts.wants_min and not facts.wants_max and problem.sense == "maximize":
        report.add("wording", "error", "The text asks to minimize, but the model maximizes.")

    _unused_numbers(problem, text, facts.numbers, facts.scale_numbers, report)


def _unused_numbers(
    problem: Problem, text: str, nums: list[Num], scale: set[float], report: AuditReport
) -> None:
    used: set[float] = set(_pairs(problem).values())
    used |= {v for _, v in _entity_values(problem).values()}
    if isinstance(problem, TransportationProblem):
        used |= {r.capacity for r in problem.routes if r.capacity is not None}
        counts = {len(problem.sources), len(problem.destinations), len(problem.routes)}
    else:
        used.add(1.0)  # default capacity / requirement, usually stated as "one"
        counts = {len(problem.agents), len(problem.tasks), len(problem.pairings)}
    ids = [i for (_, i) in _entity_values(problem)]
    for n in nums:
        if any(_close(n.value, u) for u in used) or n.value in scale or n.value in counts:
            continue
        # Skip digits that belong to an id, e.g. "Plant 3" or "L2".
        if any(
            i.lower() in text[max(0, n.start - len(i)) : n.end + len(i)].lower()
            and any(c.isdigit() for c in i)
            for i in ids
        ):
            continue
        context = text[max(0, n.start - 40) : n.end + 40].replace("\n", " ").strip()
        report.add(
            "unused_numbers", "warning",
            f"The number {n.value:g} in your text is not used anywhere in the model.",
            f"…{context}…",
        )  # fmt: skip


# --------------------------------------------------------------------------- structure + sanity


def _structure_checks(problem: Problem, report: AuditReport) -> None:
    report.checks_run.append("structure")
    pairs = _pairs(problem)
    with_pairs_from = {f for f, _ in pairs}
    with_pairs_to = {t for _, t in pairs}
    for (role, ident), (meaning, value) in _entity_values(problem).items():
        has = ident in (with_pairs_from if role == "from" else with_pairs_to)
        if not has and value > 0:
            report.add(
                "structure", "warning",
                f"{ident} has a {meaning} of {value:g} but no allowed {'route' if isinstance(problem, TransportationProblem) else 'pair'}.",
            )  # fmt: skip


def _greedy_values(problem: Problem) -> dict[str, float] | None:
    """A simple feasible plan, or None if the greedy rule gets stuck."""
    values: dict[str, float] = {}
    if isinstance(problem, TransportationProblem):
        left = {s.id: s.supply for s in problem.sources}
        for d in problem.destinations:
            need = d.demand
            for r in sorted(
                (r for r in problem.routes if r.destination == d.id), key=lambda r: r.cost
            ):
                q = min(need, left[r.source], r.capacity if r.capacity is not None else math.inf)
                if q > 0:
                    values[flow_var(r.source, d.id)] = q
                    left[r.source] -= q
                    need -= q
            if need > 1e-9:
                return None
        return values
    slots = {a.id: a.capacity for a in problem.agents}
    for t in problem.tasks:
        need = t.required
        for p in sorted((p for p in problem.pairings if p.task == t.id), key=lambda p: p.value,
                        reverse=problem.sense == "maximize"):  # fmt: skip
            if need and slots[p.agent] > 0:
                values[assign_var(p.agent, t.id)] = 1
                slots[p.agent] -= 1
                need -= 1
        if need:
            return None
    return values


def _feasible(model: LinearModel, values: dict[str, float]) -> bool:
    for c in model.constraints:
        lhs = model.activity(c, values)
        tol = 1e-6 * max(1.0, abs(c.rhs))
        if (
            (c.sense == "<=" and lhs > c.rhs + tol)
            or (c.sense == ">=" and lhs < c.rhs - tol)
            or (c.sense == "==" and abs(lhs - c.rhs) > tol)
        ):
            return False
    return True


def _sanity_checks(problem: Problem, report: AuditReport) -> None:
    report.checks_run.append("sanity")
    solved = solve_problem(problem)
    if solved.result.status != SolveStatus.OPTIMAL or solved.result.objective is None:
        return
    optimum = solved.result.objective
    model = build_model(problem)

    greedy = _greedy_values(problem)
    if greedy is not None:
        if not _feasible(model, greedy):
            report.add("sanity", "error", "A simple feasible plan is rejected by the model.")
        else:
            value = model.objective_value(greedy)
            better = (
                value < optimum - 1e-6 if problem.sense == "minimize" else value > optimum + 1e-6
            )
            if better:
                report.add(
                    "sanity", "error",
                    f"A simple greedy plan ({value:g}) beats the claimed optimum ({optimum:g}).",
                )  # fmt: skip

    if isinstance(problem, TransportationProblem):
        doubled: Problem = problem.model_copy(
            update={"routes": [r.model_copy(update={"cost": r.cost * 2}) for r in problem.routes]}
        )
    else:
        doubled = problem.model_copy(
            update={
                "pairings": [p.model_copy(update={"value": p.value * 2}) for p in problem.pairings]
            }
        )
    scaled = solve_problem(doubled).result.objective
    if scaled is None or not math.isclose(scaled, 2 * optimum, rel_tol=1e-6, abs_tol=1e-6):
        report.add(
            "sanity", "error", f"Doubling every cost gave {scaled}, expected {2 * optimum:g}."
        )


def audit(problem: Problem, text: str | None = None) -> AuditReport:
    """Run every deterministic check. `text` enables the checks against the description."""
    report = AuditReport()
    if text:
        _text_checks(problem, text, report)
    _structure_checks(problem, report)
    _sanity_checks(problem, report)
    return report

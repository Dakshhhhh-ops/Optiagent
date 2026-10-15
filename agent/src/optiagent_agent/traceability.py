"""Requirement traceability and parameter provenance.

Two tables tie the user's input to the model that will be solved:

- Requirements: each statement found in the description (a cost, a forbidden pair, a limit, the
  objective direction, a quantity) or listed by the analysis, with its interpretation, the model
  element that implements it, how that link was checked, and a status.
- Provenance: every number in the model, with where it came from (the text, an uploaded file,
  a default) and how firmly that origin is established.

Statuses are deliberately conservative:
  verified     a deterministic check tied this statement to this exact model element and value
  represented  the model contains something for it, but no deterministic check confirms the
               link (e.g. only an AI review said "covered", or the number merely appears in text)
  unresolved   missing, contradicted, ambiguous, or not checked at all: needs the user
  unsupported  the text asks for something these model types cannot express

An AI review can lower a status (flag a gap) but never raise one to "verified". The overall
formulation status is "checked" only when nothing is unresolved or unsupported.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from optiagent_agent.grounding import numbers_in
from optiagent_agent.review import Review
from optiagent_agent.textfacts import Facts, extract_facts
from optiagent_core.builders import assign_var, flow_var
from optiagent_core.ingest import AssignmentMapping, TransportationMapping
from optiagent_core.schema import AssignmentProblem, TransportationProblem

Problem = TransportationProblem | AssignmentProblem
Status = Literal["verified", "represented", "unresolved", "unsupported"]
Method = Literal[
    "text_fact", "wording", "file_data", "number_in_text", "ai_review", "pattern", "none"
]


class TraceRow(BaseModel):
    requirement: str
    """The source statement (a text snippet, or the analysis's wording)."""
    interpretation: str
    model_element: str | None = None
    units: str | None = None
    method: Method
    status: Status
    note: str = ""


class Provenance(BaseModel):
    parameter: str
    value: float
    model_element: str
    source: Literal["text", "file", "default", "unknown"]
    evidence: str | None = None
    status: Status


class TraceabilityReport(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    requirements: list[TraceRow] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    """What these checks cannot establish, shown next to the result."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def counts(self) -> dict[str, int]:
        out = {"verified": 0, "represented": 0, "unresolved": 0, "unsupported": 0}
        for status in [r.status for r in self.requirements] + [p.status for p in self.provenance]:
            out[status] += 1
        return out

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Literal["checked", "needs_review", "unsupported"]:
        c = self.counts
        if c["unsupported"]:
            return "unsupported"
        return "needs_review" if c["unresolved"] else "checked"


# --------------------------------------------------------------------------- unsupported semantics

# Each pattern names something a transportation or assignment LP cannot express. Matching is
# on the user's own text; a hit means "ask or reject", never "silently simplify".
_UNSUPPORTED: list[tuple[str, re.Pattern[str]]] = [
    (
        "Fixed or setup costs (paying once for using a route or opening a site) need yes/no "
        "decisions, which this model does not have.",
        re.compile(
            r"\b(fixed (cost|charge|fee)s?|set-?up (cost|fee)s?|opening (cost|fee)s?|"
            r"cost (of|to) open)\b",
            re.I,
        ),
    ),
    (
        "Several time periods, inventory or carrying stock between periods are not modelled.",
        re.compile(
            r"\b(inventory|holding cost|carr(y|ied|ies) over|next \d+ (weeks|months|days)|"
            r"each (week|month|day|period)|per (week|month) for)\b",
            re.I,
        ),
    ),
    (
        "A total budget cap is a constraint on the objective, which this model does not support.",
        re.compile(
            r"\b(budget|total (cost|spend(ing)?) (must|should|cannot|can't|may not) "
            r"(not )?(exceed|be (more|over|above)))\b",
            re.I,
        ),
    ),
    (
        "Limits on how many routes, suppliers or sources are used (or 'single sourcing') need "
        "yes/no decisions.",
        re.compile(
            r"\b(single[- ]sourc\w*|only one (supplier|source|plant|warehouse) (per|for each)|"
            r"at most \w+ (suppliers|sources|routes|plants|warehouses) (are |may be )?(used|open)|"
            r"must not be split|cannot be split|in full truck)\b",
            re.I,
        ),
    ),
    (
        "Whole-number lots (full trucks, pallets, batches, minimum order sizes) are not modelled; "
        "shipments are continuous.",
        re.compile(
            r"\b(full truck ?loads?|truckloads?|whole (trucks|pallets|containers)|"
            r"batches of|lots? of \d+|minimum (order|shipment|lot)( size)?|"
            r"multiples of)\b",
            re.I,
        ),
    ),
    (
        "Shipping through intermediate hubs (transshipment) is not modelled; routes go directly "
        "from a source to a destination.",
        re.compile(
            r"\b(trans-?shipment|via (a|the) (hub|depot|warehouse|cross-?dock)|"
            r"through (a|the) (hub|cross-?dock))\b",
            re.I,
        ),
    ),
    (
        "Rules linking two agents or two tasks (work together, never together, sequence, "
        "precedence) are not modelled.",
        re.compile(
            r"\b((must|should) work together|(cannot|can't|must not) work (together|with)|"
            r"not on the same (task|team|shift)|precedence|must (be done|finish) before)\b",
            re.I,
        ),
    ),
    (
        "Fairness or balancing goals (even workload, spread evenly) are a different objective.",
        re.compile(
            r"\b(balance (the )?work ?loads?|evenly|fair(ly|ness)|equal (share|number) of)\b", re.I
        ),
    ),
    (
        "Routing (visiting stops in order, tours, shortest round trip) is a different problem.",
        re.compile(
            r"\b(visit (each|every|all)|exactly once and return|round trip|tour|route the van)\b",
            re.I,
        ),
    ),
    (
        "Prices or demand that depend on decisions (non-linear revenue) are not modelled.",
        re.compile(
            r"\b(price (times|x|\*) demand|demand (falls|drops|decreases) as|elastic(ity)?)\b", re.I
        ),
    ),
]

_PERCENT = re.compile(r"\b\d+(\.\d+)?\s*(%|per ?cent)", re.I)


def unsupported_statements(text: str) -> list[TraceRow]:
    rows = []
    for meaning, pattern in _UNSUPPORTED:
        m = pattern.search(text)
        if m:
            rows.append(
                TraceRow(
                    requirement=_around(text, m.start(), m.end()),
                    interpretation=meaning,
                    method="pattern",
                    status="unsupported",
                    note="Rephrase without it, or confirm it does not apply. It was not modelled.",
                )
            )
    m = _PERCENT.search(text)
    if m:
        rows.append(
            TraceRow(
                requirement=_around(text, m.start(), m.end()),
                interpretation="A percentage is not a model input; it must have been turned into "
                "plain numbers, which may be wrong.",
                method="pattern",
                status="unresolved",
                note="Check the numbers it affects in the provenance table.",
            )
        )
    return rows


def _around(text: str, start: int, end: int, pad: int = 50) -> str:
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    return (
        ("…" if lo else "")
        + text[lo:hi].replace("\n", " ").strip()
        + ("…" if hi < len(text) else "")
    )


# --------------------------------------------------------------------------- helpers


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


class _Param(BaseModel):
    parameter: str
    value: float
    model_element: str
    key: tuple[str, str, str]
    """(kind, from-or-id, to-or-""), used to match text facts."""
    defaultable: bool = False


def _parameters(problem: Problem) -> list[_Param]:
    out: list[_Param] = []
    if isinstance(problem, TransportationProblem):
        out += [_Param(parameter=f"supply of {s.id}", value=s.supply,
                       model_element=f"supply[{s.id}] right-hand side", key=("from", s.id, ""))
                for s in problem.sources]  # fmt: skip
        out += [_Param(parameter=f"demand of {d.id}", value=d.demand,
                       model_element=f"demand[{d.id}] right-hand side", key=("to", d.id, ""))
                for d in problem.destinations]  # fmt: skip
        for r in problem.routes:
            out.append(_Param(parameter=f"cost {r.source} → {r.destination}", value=r.cost,
                              model_element=f"objective coefficient of {flow_var(r.source, r.destination)}",
                              key=("pair", r.source, r.destination)))  # fmt: skip
            if r.capacity is not None:
                out.append(_Param(parameter=f"limit {r.source} → {r.destination}", value=r.capacity,
                                  model_element=f"upper bound of {flow_var(r.source, r.destination)}",
                                  key=("limit", r.source, r.destination)))  # fmt: skip
        return out
    out += [_Param(parameter=f"value {p.agent} → {p.task}", value=p.value,
                   model_element=f"objective coefficient of {assign_var(p.agent, p.task)}",
                   key=("pair", p.agent, p.task)) for p in problem.pairings]  # fmt: skip
    out += [_Param(parameter=f"capacity of {a.id}", value=float(a.capacity),
                   model_element=f"capacity[{a.id}] right-hand side", key=("from", a.id, ""),
                   defaultable=True) for a in problem.agents]  # fmt: skip
    out += [_Param(parameter=f"agents needed for {t.id}", value=float(t.required),
                   model_element=f"cover[{t.id}] right-hand side", key=("to", t.id, ""),
                   defaultable=True) for t in problem.tasks]  # fmt: skip
    return out


def _fact_values(facts: Facts) -> dict[tuple[str, str, str], list[tuple[float | None, str]]]:
    found: dict[tuple[str, str, str], list[tuple[float | None, str]]] = defaultdict(list)
    for p in facts.pairs:
        found[("pair", p.frm, p.to)].append((p.value, p.snippet))
    for lim in facts.limits:
        found[("limit", lim.frm, lim.to)].append((lim.value, lim.snippet))
    for e in facts.entities:
        found[(e.role, e.id, "")].append((e.value, e.snippet))
    return found


def _units(problem: Problem) -> dict[str, str]:
    if isinstance(problem, TransportationProblem):
        return {"pair": "cost per unit shipped", "limit": "units", "from": "units", "to": "units"}
    word = "cost" if problem.sense == "minimize" else "score"
    return {"pair": f"{word} per assignment", "from": "tasks", "to": "agents", "limit": ""}


# --------------------------------------------------------------------------- text mode


def _text_provenance(problem: Problem, text: str, facts: Facts) -> list[Provenance]:
    stated = _fact_values(facts)
    in_text = numbers_in(text)
    rows = []
    for p in _parameters(problem):
        claims = [(v, s) for v, s in stated.get(p.key, []) if v is not None]
        values = {v for v, _ in claims}
        if len(values) > 1:
            listed = ", ".join(f"{v:g}" for v in sorted(values))
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="text", evidence=f"the text gives several values ({listed})",
                                   status="unresolved"))  # fmt: skip
        elif claims and _close(claims[0][0], p.value):
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="text", evidence=claims[0][1], status="verified"))  # fmt: skip
        elif claims:
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="text", evidence=f"the text says {claims[0][0]:g}: {claims[0][1]}",
                                   status="unresolved"))  # fmt: skip
        elif p.defaultable and _close(p.value, 1.0):
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="default", evidence="not stated; one per agent/task assumed",
                                   status="verified" if (p.key[0] in facts.default_one) else "represented"))  # fmt: skip
        elif any(_close(p.value, n) for n in in_text):
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="text", evidence="the number appears in the text, but no "
                                   "statement ties it to this element", status="represented"))  # fmt: skip
        else:
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="unknown", evidence="this number does not appear in the text",
                                   status="unresolved"))  # fmt: skip
    return rows


def _text_requirements(problem: Problem, text: str, facts: Facts) -> list[TraceRow]:
    rows: list[TraceRow] = []
    units = _units(problem)
    transport = isinstance(problem, TransportationProblem)
    pairs = (
        {(r.source, r.destination): r for r in problem.routes}
        if isinstance(problem, TransportationProblem)
        else {(p.agent, p.task): p for p in problem.pairings}
    )
    name = flow_var if transport else assign_var

    for f in facts.pairs:
        if f.value is not None:
            continue
        allowed = (f.frm, f.to) in pairs
        rows.append(TraceRow(
            requirement=f.snippet, interpretation=f"{f.frm} → {f.to} is not allowed",
            model_element=f"{name(f.frm, f.to)} absent from the model",
            method="text_fact", status="unresolved" if allowed else "verified",
            note="The model still allows it." if allowed else "",
        ))  # fmt: skip

    if facts.wants_max and facts.wants_min:
        rows.append(TraceRow(
            requirement="the text uses both minimizing and maximizing words",
            interpretation=f"The model {problem.sense}s; check this is the intended direction.",
            model_element="objective sense", method="wording", status="unresolved",
        ))  # fmt: skip
    elif facts.wants_max or facts.wants_min:
        wanted = "maximize" if facts.wants_max else "minimize"
        rows.append(TraceRow(
            requirement=f"the text asks to {wanted}",
            interpretation=f"{wanted.capitalize()} the total {'cost' if wanted == 'minimize' else 'value'}",
            model_element="objective sense", units=units["pair"], method="wording",
            status="verified" if problem.sense == wanted else "unresolved",
            note="" if problem.sense == wanted else f"The model {problem.sense}s.",
        ))  # fmt: skip
    else:
        rows.append(TraceRow(
            requirement="no minimize/maximize wording found",
            interpretation=f"The model {problem.sense}s the total",
            model_element="objective sense", method="none", status="unresolved",
            note="Confirm the objective direction.",
        ))  # fmt: skip

    if isinstance(problem, TransportationProblem):
        exact = problem.demand_constraint == "equal"
        if facts.says_at_least and exact:
            rows.append(TraceRow(
                requirement='the text says "at least"', interpretation="Destinations may receive more than demand",
                model_element="demand rows (=)", method="wording", status="unresolved",
                note="The model requires exactly the demand.",
            ))  # fmt: skip
        elif facts.says_at_least:
            rows.append(TraceRow(
                requirement='the text says "at least"', interpretation="Each destination receives at least its demand",
                model_element="demand rows (≥)", method="wording", status="verified",
            ))  # fmt: skip
        elif not exact:
            rows.append(TraceRow(
                requirement="no \"at least\" wording found", interpretation="Each destination receives at least its demand",
                model_element="demand rows (≥)", method="none", status="unresolved",
                note="The model lets destinations receive more than their demand; the text never says so.",
            ))  # fmt: skip
        stated_limits = {(f.frm, f.to) for f in facts.limits}
        for r in problem.routes:
            if r.capacity is not None and (r.source, r.destination) not in stated_limits:
                rows.append(TraceRow(
                    requirement="(no statement found)",
                    interpretation=f"{r.source} → {r.destination} carries at most {r.capacity:g}",
                    model_element=f"upper bound of {flow_var(r.source, r.destination)}", units="units",
                    method="none", status="unresolved",
                    note="The model has a route limit the text does not state.",
                ))  # fmt: skip
    return rows


# --------------------------------------------------------------------------- file mode


def _file_provenance(
    problem: Problem, mapping: TransportationMapping | AssignmentMapping
) -> list[Provenance]:
    def where(layout: object) -> str:
        d = layout.model_dump() if isinstance(layout, BaseModel) else {}
        cols = [d.get(k) for k in ("value_column", "capacity_column", "row_id_column") if d.get(k)]
        return f"table {d.get('table')!r}" + (
            f", column(s) {', '.join(map(repr, cols))}" if cols else ""
        )

    rows = []
    for p in _parameters(problem):
        kind = p.key[0]
        if isinstance(mapping, TransportationMapping):
            layout: object = {"pair": mapping.costs, "limit": mapping.costs,
                              "from": mapping.supply, "to": mapping.demand}[kind]  # fmt: skip
        else:
            layout = {"pair": mapping.values, "from": mapping.agent_capacity,
                      "to": mapping.task_required}.get(kind)  # fmt: skip
        if layout is None:
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="default", evidence="no table mapped; one per agent/task assumed",
                                   status="represented"))  # fmt: skip
        else:
            rows.append(Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                                   source="file", evidence=f"read by code from {where(layout)}",
                                   status="verified"))  # fmt: skip
    return rows


# --------------------------------------------------------------------------- entry point

LIMITATIONS = [
    "Text facts are read by fixed patterns. A statement phrased in an unusual way may not be "
    "linked, and then shows as 'represented' or 'unresolved' rather than 'verified'.",
    "'Verified' means a stated value or rule matches the model exactly. It does not prove the "
    "description itself is complete or correct.",
    "AI review results are opinions. They can flag a gap but never mark anything verified.",
]


def trace(
    problem: Problem,
    text: str | None = None,
    *,
    mapping: TransportationMapping | AssignmentMapping | None = None,
    requirements: list[str] | None = None,
    review: Review | None = None,
) -> TraceabilityReport:
    report = TraceabilityReport(limitations=LIMITATIONS)
    if mapping is not None:
        report.provenance = _file_provenance(problem, mapping)
    elif text:
        facts = extract_facts(text, problem)
        report.provenance = _text_provenance(problem, text, facts)
        report.requirements = _text_requirements(problem, text, facts)
    else:
        report.provenance = [
            Provenance(parameter=p.parameter, value=p.value, model_element=p.model_element,
                       source="unknown", evidence="entered directly; no description to check against",
                       status="represented")
            for p in _parameters(problem)
        ]  # fmt: skip
    if text:
        report.requirements += unsupported_statements(text)

    checks = review.checks if review is not None else []
    for i, requirement in enumerate(requirements or []):
        check = checks[i] if i < len(checks) else None
        if check is None:
            report.requirements.append(TraceRow(
                requirement=requirement, interpretation="Not reviewed", method="none",
                status="unresolved", note="No check linked this requirement to the model.",
            ))  # fmt: skip
        elif check.status == "not_applicable":
            continue
        else:
            report.requirements.append(TraceRow(
                requirement=requirement, interpretation=check.reason or check.status,
                model_element=check.where or None, method="ai_review",
                status="represented" if check.status == "covered" else "unresolved",
                note="AI review, not a proof." if check.status == "covered" else f"AI review: {check.status}.",
            ))  # fmt: skip
    return report

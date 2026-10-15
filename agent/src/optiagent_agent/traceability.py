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
        "Fixed or setup costs (paying once for using a route, a vehicle or a site) need yes/no "
        "decisions, which this model does not have.",
        re.compile(
            r"\b(fixed (cost|charge|fee)s?|set-?up (cost|fee)s?|opening (cost|fee)s?|"
            r"cost (of|to) (open|keep)|keep (it |them )?open|whether to open|"
            r"which (\w+ ){0,2}to (open|keep|close|rent)|(rental|rent) fee|"
            r"(decide|choose) how many \w+ to (rent|open|use|buy))\b",
            re.I,
        ),
    ),
    (
        "Several time periods, inventory or carrying stock between periods are not modelled.",
        re.compile(
            r"\b(inventory|holding cost|carr(y|ied|ies) over|next \d+ (weeks|months|days)|"
            r"each (week|month|day|period)|per (week|month) for|stored for the following|"
            r"between (months|weeks|periods))\b",
            re.I,
        ),
    ),
    (
        "A cap on total spend, emissions or capital is a side constraint this model does not "
        "support.",
        re.compile(
            r"\b((budget|spend(ing)?|capital) (limit|cap|ceiling)|budget of \d|"
            r"within (a|our|the) budget|total (cost|spend(ing)?) (must|should|cannot|can't|may) "
            r"(not )?(exceed|be (more|over|above))|(emissions?|co2|carbon)\b[^.]{0,30}"
            r"\b(below|under|at most|cap|limit))",
            re.I,
        ),
    ),
    (
        "Limits on how many routes, suppliers or sites are used (or single sourcing) need yes/no "
        "decisions.",
        re.compile(
            r"\b(single[- ]sourc\w*|only one (supplier|source|plant|warehouse|depot) (per|for each)|"
            r"(at most|no more than|only) \w+ of the (\w+ )?(plants|suppliers|sources|warehouses|"
            r"depots|sites|routes)|at most \w+ (suppliers|sources|routes|plants|warehouses) "
            r"(are |may be )?(used|open)|(must not|cannot|can't) be (split|divided)|"
            r"(entirely|all of its \w+) from one|in full truck)\b",
            re.I,
        ),
    ),
    (
        "Whole-number lots (trucks, containers, pallets, batches, minimum order sizes) are not "
        "modelled; shipments are continuous.",
        re.compile(
            r"\b(full truck ?loads?|truckloads?|whole (trucks|pallets|containers)|"
            r"batches of|lots? of \d+|minimum (order|shipment|lot)( size)?|multiples of|"
            r"pay per (truck|container|vehicle|van|trip)|(trucks?|containers?|vans?) "
            r"(carry|carries|hold|holds) (exactly )?\d+)\b",
            re.I,
        ),
    ),
    (
        "Shipping through intermediate hubs (transshipment) is not modelled; routes go directly "
        "from a source to a destination.",
        re.compile(
            r"\b(trans-?shipment|(via|through) (\w+ ){0,3}(hubs?|cross-?docks?)|"
            r"to (\w+ )?hubs? and then|regional hubs?)\b",
            re.I,
        ),
    ),
    (
        "Rules linking two agents, two tasks or consecutive periods (work together, never "
        "together, sequence, precedence) are not modelled.",
        re.compile(
            r"\b((must|should) work together|(cannot|can't|must not) work (together|with)|"
            r"not on the same (task|team|shift)|precedence|(finished|completed|done|finish) "
            r"before|in a row|consecutive|(order|sequence) in which)\b",
            re.I,
        ),
    ),
    (
        "Fairness or balancing goals (even workload, same number each) are a different objective.",
        re.compile(
            r"\b(balance (the )?work ?loads?|evenly|fair(ly|ness)|equal (share|number) of|"
            r"(roughly|about) the same (number|amount)|overloaded)\b",
            re.I,
        ),
    ),
    (
        "Routing (visiting stops in order, tours, shortest round trip) is a different problem.",
        re.compile(
            r"\b(visit (each|every|all)|visits each|exactly once and return|round trip|tour|"
            r"route the van)\b",
            re.I,
        ),
    ),
    (
        "Prices or demand that depend on decisions (non-linear revenue) are not modelled.",
        re.compile(
            r"\b(price (times|x|\*) demand|demand (falls|drops|decreases) as|elastic(ity)?|"
            r"(choose|set) (the )?price)\b",
            re.I,
        ),
    ),
    (
        "Choosing which projects or items to fund (selection, portfolios) is a different problem.",
        re.compile(r"\b(portfolio|which projects to fund|projects to fund)\b", re.I),
    ),
]

# "Spreading evenly is not required": a pattern inside a negated clause is not a requirement.
_NEGATED = re.compile(
    r"\b(not (required|needed|necessary|a requirement)|no need|don't need)\b", re.I
)


def _clause_around(text: str, start: int, end: int) -> str:
    lo = max(text.rfind(".", 0, start), text.rfind(";", 0, start)) + 1
    hi = min((i for i in (text.find(".", end), text.find(";", end)) if i != -1), default=len(text))
    return text[lo:hi]


_PERCENT = re.compile(r"\b\d+(\.\d+)?\s*(%|per ?cent)", re.I)

# A unit only counts when it follows a number ("20 tons", "500kg"), not as a word on its own.
_N = r"\d[\d,]*(\.\d+)?\s*"
_UNITS: dict[str, dict[str, re.Pattern[str]]] = {
    "weight": {
        "kg": re.compile(_N + r"(kg|kgs|kilo(gram)?s?)\b", re.I),
        "tonnes": re.compile(_N + r"(t|tons?|tonnes?|mt)\b", re.I),
        "pounds": re.compile(_N + r"(lbs?|pounds?)\b", re.I),
    },
    "volume": {
        "litres": re.compile(_N + r"(l|litres?|liters?)\b", re.I),
        "millilitres": re.compile(_N + r"(ml|millilit(re|er)s?)\b", re.I),
        "gallons": re.compile(_N + r"(gal|gallons?)\b", re.I),
    },
    "distance": {
        "km": re.compile(_N + r"(km|kilomet(re|er)s?)\b", re.I),
        "miles": re.compile(_N + r"(mi|miles?)\b", re.I),
    },
    "time": {
        "minutes": re.compile(_N + r"(min|mins|minutes?)\b", re.I),
        "hours": re.compile(_N + r"(h|hrs?|hours?)\b", re.I),
        "days": re.compile(_N + r"days?\b", re.I),
    },
}


def unsupported_statements(text: str) -> list[TraceRow]:
    rows = []
    for meaning, pattern in _UNSUPPORTED:
        m = next(
            (m for m in pattern.finditer(text)
             if not _NEGATED.search(_clause_around(text, m.start(), m.end()))),
            None,
        )  # fmt: skip
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
    for dimension, units in _UNITS.items():
        found = {}
        for unit, pattern in units.items():
            hit = pattern.search(text)
            if hit:
                found[unit] = hit
        if len(found) > 1:
            first = min(found.values(), key=lambda h: h.start())
            rows.append(
                TraceRow(
                    requirement=_around(text, first.start(), first.end()),
                    interpretation=f"The {dimension}s are given in different units "
                    f"({', '.join(sorted(found))}). The model has no units, so they must have "
                    "been converted to one, which may be wrong.",
                    method="pattern",
                    status="unresolved",
                    note="State every quantity in the same unit, or check each converted number.",
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

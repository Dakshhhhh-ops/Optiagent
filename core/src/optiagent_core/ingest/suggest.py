"""Heuristic column-mapping suggestions (the non-LLM baseline).

Tables are matched mainly by id overlap: a key/value table whose ids are the cost table's
row ids is the supply table, whatever its columns are called. Names only break ties.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from optiagent_core.ingest.mapping import (
    AssignmentMapping,
    KeyValue,
    LongLayout,
    MatrixLayout,
    TransportationMapping,
)
from optiagent_core.ingest.tables import Table, TableProfile, as_text, profile_table

COST = {"cost", "costs", "price", "rate", "freight", "tariff", "distance", "time"}
SUPPLY = {
    "supply",
    "capacity",
    "available",
    "availability",
    "production",
    "stock",
    "inventory",
    "output",
}
DEMAND = {"demand", "requirement", "requirements", "required", "need", "needs", "order", "orders"}
FROM = {"from", "source", "origin", "plant", "factory", "warehouse", "supplier", "silo", "depot"}
TO = {"to", "destination", "dest", "customer", "market", "store", "city", "mill", "sink", "region"}
AGENT = {"agent", "worker", "employee", "person", "ta", "staff", "student", "name", "machine"}
TASK = {"task", "job", "lab", "shift", "project", "section", "course", "slot", "role"}
SCORE = {
    "preference",
    "preferences",
    "score",
    "rating",
    "utility",
    "satisfaction",
    "profit",
    "benefit",
}
CAPACITY = {"capacity", "max", "maximum", "load", "limit", "slots"}
REQUIRED = {"required", "requirement", "need", "needed", "needs", "positions", "seats", "count"}


class Suggestion(BaseModel):
    mapping: TransportationMapping | AssignmentMapping | None
    notes: list[str]


def _tokens(text: str) -> set[str]:
    return set(re.split(r"[^a-z0-9]+", text.lower())) - {""}


def _score(text: str, words: set[str]) -> int:
    return len(_tokens(text) & words)


def _cols(profile: TableProfile, dtype: Literal["number", "text"]) -> list[str]:
    return [c.name for c in profile.columns if c.dtype == dtype]


def _best(
    columns: list[str], words: set[str], exclude: frozenset[str] | set[str] = frozenset()
) -> str | None:
    candidates = [c for c in columns if c not in exclude]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (_score(c, words), -candidates.index(c)))


def _ids(table: Table, column: str) -> set[str]:
    return {v for v in (as_text(x) for x in table.column_values(column)) if v is not None}


def _pair_layout(
    table: Table,
    profile: TableProfile,
    from_words: set[str],
    to_words: set[str],
    value_words: set[str],
) -> tuple[LongLayout | MatrixLayout, set[str], set[str]] | None:
    """Recognise a long or matrix pair table. Returns the layout and its from/to id sets."""
    text, numbers = _cols(profile, "text"), _cols(profile, "number")
    if len(text) >= 2 and numbers:
        frm = _best(text, from_words) or text[0]
        to = _best(text, to_words, {frm}) or text[1]
        value = _best(numbers, value_words) or numbers[0]
        capacity = next(
            (c for c in numbers if c != value and _score(c, CAPACITY | {"cap", "upper"})), None
        )
        layout = LongLayout(
            table=table.name,
            from_column=frm,
            to_column=to,
            value_column=value,
            capacity_column=capacity,
        )
        return layout, _ids(table, frm), _ids(table, to)
    if text and len(numbers) >= 2 and profile.columns[0].dtype == "text":
        row_id = profile.columns[0].name
        # A numeric column that looks like supply/demand is a side column, not a destination.
        ignore = [c for c in numbers if _score(c, SUPPLY | DEMAND | {"total"})]
        to_ids = {c.name for c in profile.columns[1:] if c.name not in ignore}
        matrix = MatrixLayout(table=table.name, row_id_column=row_id, ignore_columns=ignore)
        return matrix, _ids(table, row_id), to_ids
    return None


def _key_value_tables(
    tables: list[Table], profiles: dict[str, TableProfile], skip: str
) -> list[tuple[Table, str, list[str]]]:
    """Tables with one id column and at least one numeric column."""
    out = []
    for t in tables:
        if t.name == skip:
            continue
        text, numbers = _cols(profiles[t.name], "text"), _cols(profiles[t.name], "number")
        if text and numbers:
            out.append((t, text[0], numbers))
        elif not text and len(numbers) >= 2:
            # Numeric ids (e.g. plant 1, 2, 3): treat the first column as the id.
            out.append((t, numbers[0], numbers[1:]))
    return out


def _match_key_value(
    candidates: list[tuple[Table, str, list[str]]], ids: set[str], words: set[str], used: set[str]
) -> KeyValue | None:
    best: tuple[float, KeyValue] | None = None
    for table, id_col, numbers in candidates:
        if table.name in used:
            continue
        table_ids = _ids(table, id_col)
        if not table_ids:
            continue
        overlap = len(table_ids & ids) / max(len(table_ids | ids), 1)
        value_col = _best(numbers, words) or numbers[0]
        score = overlap * 10 + _score(table.name, words) + _score(value_col, words)
        if overlap > 0 and (best is None or score > best[0]):
            best = (score, KeyValue(table=table.name, id_column=id_col, value_column=value_col))
    return best[1] if best else None


def _pick_pair_table(
    tables: list[Table],
    profiles: dict[str, TableProfile],
    from_w: set[str],
    to_w: set[str],
    value_w: set[str],
) -> tuple[LongLayout | MatrixLayout, set[str], set[str]] | None:
    scored = []
    for t in tables:
        found = _pair_layout(t, profiles[t.name], from_w, to_w, value_w)
        if found:
            size = len(found[1]) * len(found[2])
            scored.append((_score(t.name, value_w), size, found))
    if not scored:
        return None
    return max(scored, key=lambda s: (s[0], s[1]))[2]


def suggest_mapping(
    tables: list[Table], kind: Literal["transportation", "assignment"]
) -> Suggestion:
    profiles = {t.name: profile_table(t, preview_rows=0) for t in tables}
    notes: list[str] = []

    if kind == "transportation":
        pair = _pick_pair_table(tables, profiles, FROM, TO, COST)
        if pair is None:
            return Suggestion(mapping=None, notes=["no table looks like a cost table"])
        layout, sources, destinations = pair
        notes.append(f"costs from {layout.table!r} ({layout.layout} layout)")
        kv = _key_value_tables(tables, profiles, skip=layout.table)
        supply = _match_key_value(kv, sources, SUPPLY, set())
        demand = _match_key_value(kv, destinations, DEMAND, {supply.table} if supply else set())
        if supply is None or demand is None:
            missing = [n for n, v in (("supply", supply), ("demand", demand)) if v is None]
            notes.append(f"could not find a {' or '.join(missing)} table")
            return Suggestion(mapping=None, notes=notes)
        notes += [f"supply from {supply.table!r}", f"demand from {demand.table!r}"]
        return Suggestion(
            mapping=TransportationMapping(costs=layout, supply=supply, demand=demand), notes=notes
        )

    pair = _pick_pair_table(tables, profiles, AGENT, TASK, SCORE | COST)
    if pair is None:
        return Suggestion(mapping=None, notes=["no table looks like an agent-task table"])
    layout, agents, task_ids = pair
    value_name = layout.value_column if isinstance(layout, LongLayout) else layout.table
    sense: Literal["minimize", "maximize"] = "maximize" if _score(value_name, SCORE) else "minimize"
    notes.append(f"values from {layout.table!r} ({layout.layout} layout), {sense}")
    kv = _key_value_tables(tables, profiles, skip=layout.table)
    capacity = _match_key_value(kv, agents, CAPACITY, set())
    required = _match_key_value(kv, task_ids, REQUIRED, {capacity.table} if capacity else set())
    if capacity:
        notes.append(f"agent capacity from {capacity.table!r}")
    if required:
        notes.append(f"task requirements from {required.table!r}")
    return Suggestion(
        mapping=AssignmentMapping(
            sense=sense, values=layout, agent_capacity=capacity, task_required=required
        ),
        notes=notes,
    )

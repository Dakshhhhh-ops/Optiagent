"""Column mappings and the deterministic loader: tables + mapping -> typed problem.

A mapping only says *where* values live. This module reads them, so a wrong number can
only come from the user's file, never from the LLM.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

from optiagent_core.ingest.tables import Cell, Table, as_text, is_missing, parse_number
from optiagent_core.schema import (
    Agent,
    AssignmentProblem,
    Destination,
    Pairing,
    Route,
    Source,
    Task,
    TransportationProblem,
)

BLOCKED_TOKENS = frozenset({"x", "blocked", "n/a", "na", "-", "inf", "infinity", "∞"})


def _is_blocked(raw: Cell) -> bool:
    return is_missing(raw) or (isinstance(raw, str) and raw.strip().lower() in BLOCKED_TOKENS)


# --------------------------------------------------------------------------- mapping specs


class LongLayout(BaseModel):
    """One row per pair: from, to, value (and optionally a per-pair capacity)."""

    layout: Literal["long"] = "long"
    table: str
    from_column: str
    to_column: str
    value_column: str
    capacity_column: str | None = None


class MatrixLayout(BaseModel):
    """One row per 'from' id; every other column is a 'to' id holding the value.

    Blank, 'x', '-', 'n/a' or 'inf' cells mean the pair is not allowed.
    """

    layout: Literal["matrix"] = "matrix"
    table: str
    row_id_column: str
    ignore_columns: list[str] = Field(default_factory=list)


PairLayout = Annotated[LongLayout | MatrixLayout, Field(discriminator="layout")]


class KeyValue(BaseModel):
    """A table with an id column and a numeric value column."""

    table: str
    id_column: str
    value_column: str


class TransportationMapping(BaseModel):
    kind: Literal["transportation"] = "transportation"
    name: str = "Transportation problem"
    sense: Literal["minimize", "maximize"] = "minimize"
    demand_constraint: Literal["equal", "at_least"] = "equal"
    costs: PairLayout
    supply: KeyValue
    demand: KeyValue


class AssignmentMapping(BaseModel):
    kind: Literal["assignment"] = "assignment"
    name: str = "Assignment problem"
    sense: Literal["minimize", "maximize"] = "minimize"
    values: PairLayout
    agent_capacity: KeyValue | None = None
    """Optional. Without it every agent can take one task."""
    task_required: KeyValue | None = None
    """Optional. Without it every task needs one agent."""


Mapping = Annotated[TransportationMapping | AssignmentMapping, Field(discriminator="kind")]


# --------------------------------------------------------------------------- results


class DataIssue(BaseModel):
    severity: Literal["error", "warning", "info"]
    message: str
    table: str | None = None
    row: int | None = None
    """Spreadsheet row number (header is row 1)."""
    column: str | None = None


class LoadResult(BaseModel):
    problem: TransportationProblem | AssignmentProblem | None
    issues: list[DataIssue]

    @property
    def ok(self) -> bool:
        return self.problem is not None


class _Issues(list[DataIssue]):
    def add(
        self,
        severity: Literal["error", "warning", "info"],
        message: str,
        table: str | None = None,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        self.append(
            DataIssue(severity=severity, message=message, table=table, row=row, column=column)
        )

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self)


class _MappingError(Exception):
    pass


def _table(tables: dict[str, Table], name: str) -> Table:
    if name not in tables:
        raise _MappingError(f"no table named {name!r}")
    return tables[name]


def _col(table: Table, column: str) -> int:
    try:
        return table.column_index(column)
    except KeyError as exc:
        raise _MappingError(str(exc.args[0])) from None


def _rows(table: Table) -> Iterator[tuple[int, list[Cell]]]:
    for i, row in enumerate(table.rows):
        yield i + 2, list(row)  # +1 for header, +1 for 1-based rows


# --------------------------------------------------------------------------- readers


class _Pair(BaseModel):
    frm: str
    to: str
    value: float
    capacity: float | None = None


def _read_pairs(
    tables: dict[str, Table], layout: LongLayout | MatrixLayout, issues: _Issues
) -> list[_Pair]:
    table = _table(tables, layout.table)
    pairs: list[_Pair] = []
    seen: dict[tuple[str, str], int] = {}

    def add(pair: _Pair, row: int, column: str | None) -> None:
        key = (pair.frm, pair.to)
        if key in seen:
            issues.add(
                "error",
                f"{pair.frm} → {pair.to} appears twice (rows {seen[key]} and {row})",
                table.name,
                row,
                column,
            )
            return
        seen[key] = row
        pairs.append(pair)

    if isinstance(layout, LongLayout):
        fi, ti, vi = (
            _col(table, c) for c in (layout.from_column, layout.to_column, layout.value_column)
        )
        ci = _col(table, layout.capacity_column) if layout.capacity_column else None
        for row, cells in _rows(table):
            frm, to = as_text(cells[fi]), as_text(cells[ti])
            if frm is None or to is None:
                issues.add("warning", "row skipped: missing id", table.name, row)
                continue
            raw = cells[vi]
            if _is_blocked(raw):
                issues.add(
                    "info",
                    f"{frm} → {to} has no value, treated as not allowed",
                    table.name,
                    row,
                    layout.value_column,
                )
                continue
            value = parse_number(raw)
            if value is None:
                issues.add(
                    "error", f"value {raw!r} is not a number", table.name, row, layout.value_column
                )
                continue
            capacity = None
            if ci is not None and not is_missing(cells[ci]):
                capacity = parse_number(cells[ci])
                if capacity is None or capacity < 0:
                    issues.add(
                        "error",
                        f"capacity {cells[ci]!r} must be a non-negative number",
                        table.name,
                        row,
                        layout.capacity_column,
                    )
                    continue
            add(_Pair(frm=frm, to=to, value=value, capacity=capacity), row, layout.value_column)
        return pairs

    ri = _col(table, layout.row_id_column)
    ignored = set(layout.ignore_columns) | {layout.row_id_column}
    to_columns = [(i, c) for i, c in enumerate(table.columns) if c not in ignored]
    if not to_columns:
        raise _MappingError(f"matrix table {table.name!r} has no value columns")
    blocked = 0
    for row, cells in _rows(table):
        frm = as_text(cells[ri])
        if frm is None:
            issues.add("warning", "row skipped: missing id", table.name, row, layout.row_id_column)
            continue
        for i, to in to_columns:
            raw = cells[i]
            if _is_blocked(raw):
                blocked += 1
                continue
            value = parse_number(raw)
            if value is None:
                issues.add("error", f"value {raw!r} is not a number", table.name, row, to)
                continue
            add(_Pair(frm=frm, to=to, value=value), row, to)
    if blocked:
        issues.add("info", f"{blocked} empty or blocked cell(s) treated as not allowed", table.name)
    return pairs


def _read_key_values(
    tables: dict[str, Table], spec: KeyValue, issues: _Issues, *, integer: bool = False
) -> dict[str, float]:
    table = _table(tables, spec.table)
    ii, vi = _col(table, spec.id_column), _col(table, spec.value_column)
    values: dict[str, float] = {}
    rows: dict[str, int] = {}
    for row, cells in _rows(table):
        key = as_text(cells[ii])
        if key is None:
            issues.add("warning", "row skipped: missing id", table.name, row, spec.id_column)
            continue
        value = parse_number(cells[vi])
        if value is None:
            issues.add(
                "error",
                f"{key}: value {cells[vi]!r} is not a number",
                table.name,
                row,
                spec.value_column,
            )
            continue
        if value < 0:
            issues.add(
                "error", f"{key}: value {value:g} is negative", table.name, row, spec.value_column
            )
            continue
        if integer and not value.is_integer():
            issues.add(
                "error",
                f"{key}: value {value:g} must be a whole number",
                table.name,
                row,
                spec.value_column,
            )
            continue
        if key in values:
            issues.add(
                "error",
                f"{key} appears twice (rows {rows[key]} and {row})",
                table.name,
                row,
                spec.id_column,
            )
            continue
        values[key], rows[key] = value, row
    return values


def _cross_reference(
    pair_ids: set[str], table_ids: set[str], role: str, table: str, issues: _Issues
) -> None:
    for missing in sorted(pair_ids - table_ids):
        issues.add("error", f"{role} {missing!r} has costs but no row in {table}", table)
    for unused in sorted(table_ids - pair_ids):
        issues.add("warning", f"{role} {unused!r} has no allowed pairs and will be unused", table)


# --------------------------------------------------------------------------- loaders


def _finish(
    build: type[TransportationProblem] | type[AssignmentProblem],
    data: dict[str, object],
    issues: _Issues,
) -> LoadResult:
    if issues.has_errors:
        return LoadResult(problem=None, issues=issues)
    try:
        problem = build.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            issues.add("error", f"{'.'.join(map(str, err['loc']))}: {err['msg']}")
        return LoadResult(problem=None, issues=issues)
    return LoadResult(problem=problem, issues=issues)


def _load_transportation(
    tables: dict[str, Table], m: TransportationMapping, issues: _Issues
) -> LoadResult:
    pairs = _read_pairs(tables, m.costs, issues)
    supply = _read_key_values(tables, m.supply, issues)
    demand = _read_key_values(tables, m.demand, issues)
    _cross_reference({p.frm for p in pairs}, set(supply), "source", m.supply.table, issues)
    _cross_reference({p.to for p in pairs}, set(demand), "destination", m.demand.table, issues)
    if not pairs:
        issues.add("error", "no allowed routes were found", m.costs.table)
    return _finish(
        TransportationProblem,
        {
            "name": m.name,
            "sense": m.sense,
            "demand_constraint": m.demand_constraint,
            "sources": [Source(id=k, supply=v) for k, v in supply.items()],
            "destinations": [Destination(id=k, demand=v) for k, v in demand.items()],
            "routes": [
                Route(source=p.frm, destination=p.to, cost=p.value, capacity=p.capacity)
                for p in pairs
                if p.frm in supply and p.to in demand
            ],
        },
        issues,
    )


def _load_assignment(tables: dict[str, Table], m: AssignmentMapping, issues: _Issues) -> LoadResult:
    pairs = _read_pairs(tables, m.values, issues)
    agents_in_pairs = list(dict.fromkeys(p.frm for p in pairs))
    tasks_in_pairs = list(dict.fromkeys(p.to for p in pairs))

    capacity: dict[str, float] = {a: 1 for a in agents_in_pairs}
    if m.agent_capacity:
        given = _read_key_values(tables, m.agent_capacity, issues, integer=True)
        _cross_reference(set(agents_in_pairs), set(given), "agent", m.agent_capacity.table, issues)
        capacity = given
    else:
        issues.add("info", "no agent capacity table: each agent takes at most 1 task")

    required: dict[str, float] = {t: 1 for t in tasks_in_pairs}
    if m.task_required:
        given = _read_key_values(tables, m.task_required, issues, integer=True)
        _cross_reference(set(tasks_in_pairs), set(given), "task", m.task_required.table, issues)
        required = given
    else:
        issues.add("info", "no task requirement table: each task needs exactly 1 agent")

    if not pairs:
        issues.add("error", "no allowed pairs were found", m.values.table)
    return _finish(
        AssignmentProblem,
        {
            "name": m.name,
            "sense": m.sense,
            "agents": [Agent(id=k, capacity=int(v)) for k, v in capacity.items()],
            "tasks": [Task(id=k, required=int(v)) for k, v in required.items()],
            "pairings": [
                Pairing(agent=p.frm, task=p.to, value=p.value)
                for p in pairs
                if p.frm in capacity and p.to in required
            ],
        },
        issues,
    )


def load_problem(
    tables: list[Table], mapping: TransportationMapping | AssignmentMapping
) -> LoadResult:
    by_name = {t.name: t for t in tables}
    issues = _Issues()
    try:
        if isinstance(mapping, TransportationMapping):
            return _load_transportation(by_name, mapping, issues)
        return _load_assignment(by_name, mapping, issues)
    except _MappingError as exc:
        issues.add("error", str(exc))
        return LoadResult(problem=None, issues=issues)

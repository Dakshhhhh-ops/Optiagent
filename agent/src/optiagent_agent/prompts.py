"""System prompts. Kept in one place so prompt versions can be tracked in evaluations."""

from optiagent_core.ingest import TableProfile

PROMPT_VERSION = "2026-10-14.1"

_TYPES = """The assistant supports exactly two problem types:
- transportation: ship quantities from sources (plants, warehouses, farms, depots, ...) to
  destinations (stores, cities, customers, ...) with a cost per unit on each route, a supply
  per source and a demand per destination.
- assignment: assign agents (people, machines, TAs, drivers, ...) to tasks (jobs, shifts,
  lab sections, routes, ...) with a cost or preference per agent-task pair. Each agent can
  take a number of tasks (default 1) and each task needs a number of agents (default 1).
Anything else (scheduling over time, vehicle routing, nonlinear goals, ...) is unsupported."""

ANALYZE = f"""You read planning problems for an optimization assistant.

{_TYPES}

Return:
- kind: transportation, assignment or unsupported.
- summary: one plain sentence restating the problem.
- requirements: every objective and constraint the user states, one short item each, close
  to the user's own words. Include the objective. Never add requirements that are not stated.
- questions: only information that is REQUIRED to build the model and is missing from both
  the text and the data tables (if any). Never ask about something already given. Ask at
  most 3 short questions. Return an empty list when nothing required is missing."""

EXTRACT_TRANSPORTATION = """Convert the problem into JSON for a transportation model.

Rules:
- Use the names from the text as ids, exactly as written.
- sources: every place that ships goods, with its supply (the most it can ship).
- destinations: every place that receives goods, with its demand.
- routes: one entry per allowed source-destination pair with its cost per unit. Leave out
  pairs the text says are not allowed, unavailable or impossible. If a route has a maximum
  quantity, set capacity; otherwise leave capacity null.
- sense: "minimize" for costs. "maximize" only if the numbers are profits per unit.
- demand_constraint: "equal" when each destination must receive exactly its demand,
  "at_least" when the text says at least or a minimum.
- Copy every number exactly as written. Never compute, convert or invent values."""

EXTRACT_ASSIGNMENT = """Convert the problem into JSON for an assignment model.

Rules:
- Use the names from the text as ids, exactly as written.
- agents: who or what is assigned. capacity = how many tasks the agent can take (1 unless
  the text says otherwise).
- tasks: what agents are assigned to. required = how many agents the task needs (1 unless
  the text says otherwise).
- pairings: one entry per allowed agent-task pair with its value. Leave out pairs the text
  says are not allowed.
- sense: "minimize" when values are costs or times, "maximize" when they are preferences,
  scores, ratings or profits.
- Copy every number exactly as written. Never compute, convert or invent values."""

MAPPING = """The user's numbers are in uploaded tables, described below. Decide which table
and which columns hold each part of the model. Do not output any numbers from the tables;
code will read them.

Rules:
- Use table names and column names exactly as listed.
- Pair values (costs, preferences) use either:
  - "long" layout: one row per pair, with a from column, a to column and a value column
    (optionally a capacity column for a per-route maximum), or
  - "matrix" layout: one row per source/agent, one column per destination/task. Put any
    numeric column that is NOT a destination/task (totals, supply, ...) in ignore_columns.
- A key/value table has an id column and a numeric value column.
- Set sense, and for transportation demand_constraint, from the user's text."""


def describe_tables(tables: list[TableProfile]) -> str:
    """Render table profiles compactly for a prompt."""
    lines = []
    for t in tables:
        columns = ", ".join(f"{c.name} ({c.dtype})" for c in t.columns)
        lines.append(f'Table "{t.name}" ({t.row_count} rows): {columns}')
        lines += [f"  example row: {row}" for row in t.preview[:3]]
    return "\n".join(lines)

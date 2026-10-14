"""Generate natural-language problems with known answers.

Each problem is built as a typed spec first and then rendered to text, so the correct model is
known by construction and the expected optimum comes from the deterministic solver.

    uv run python -m optiagent_eval.generate            # writes eval/data/nl_v1.jsonl
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from optiagent_core.pipeline import solve_problem
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
from optiagent_core.solver import SolveStatus

DATASET = "nl_v1"
SEED = 20261014


class Item(BaseModel):
    id: str
    kind: Literal["transportation", "assignment", "unsupported"]
    style: str
    features: list[str]
    text: str
    problem: TransportationProblem | AssignmentProblem | None = None
    expected_objective: float | None = None


# --------------------------------------------------------------------------- vocab

TRANSPORT_DOMAINS: list[dict[str, Any]] = [
    {"src": "warehouse", "dst": "store", "unit": "units", "money": "₹",
     "srcs": ["Mumbai", "Delhi", "Chennai", "Kolkata"],
     "dsts": ["Pune", "Jaipur", "Bengaluru", "Hyderabad", "Lucknow"]},
    {"src": "factory", "dst": "city", "unit": "tons", "money": "$",
     "srcs": ["Plant A", "Plant B", "Plant C", "Plant D"],
     "dsts": ["Austin", "Denver", "Boston", "Seattle", "Miami"]},
    {"src": "farm", "dst": "market", "unit": "crates", "money": "$",
     "srcs": ["Green Acres", "Sunny Fields", "Hill Farm", "River Farm"],
     "dsts": ["North Market", "South Market", "East Market", "West Market", "Central Market"]},
    {"src": "blood bank", "dst": "hospital", "unit": "bags", "money": "€",
     "srcs": ["Bank 1", "Bank 2", "Bank 3", "Bank 4"],
     "dsts": ["St Mary", "City General", "Royal", "Riverside", "Northgate"]},
    {"src": "depot", "dst": "customer", "unit": "pallets", "money": "$",
     "srcs": ["Depot X", "Depot Y", "Depot Z", "Depot W"],
     "dsts": ["Acme", "Globex", "Initech", "Umbrella", "Hooli"]},
]  # fmt: skip

ASSIGN_DOMAINS: list[dict[str, Any]] = [
    {"agent": "worker", "task": "job", "value": "hours", "sense": "minimize",
     "agents": ["Asha", "Ben", "Chen", "Dina", "Eli"], "tasks": ["Welding", "Painting", "Assembly", "Testing"]},
    {"agent": "TA", "task": "lab section", "value": "preference score", "sense": "maximize",
     "agents": ["Ravi", "Meera", "Tom", "Lena", "Omar"], "tasks": ["L1", "L2", "L3", "L4"]},
    {"agent": "nurse", "task": "shift", "value": "cost", "sense": "minimize",
     "agents": ["Nurse Kim", "Nurse Lopez", "Nurse Patel", "Nurse Brown", "Nurse Ali"],
     "tasks": ["Morning", "Evening", "Night", "Weekend"]},
    {"agent": "driver", "task": "route", "value": "cost", "sense": "minimize",
     "agents": ["Driver 1", "Driver 2", "Driver 3", "Driver 4", "Driver 5"],
     "tasks": ["Route North", "Route South", "Route East", "Route West"]},
    {"agent": "consultant", "task": "client", "value": "rating", "sense": "maximize",
     "agents": ["Ana", "Bo", "Cy", "Dev", "Eva"], "tasks": ["Client Alpha", "Client Beta", "Client Gamma", "Client Delta"]},
]  # fmt: skip

UNSUPPORTED = [
    "A delivery van starts at the depot and must visit 6 customers exactly once and return, "
    "travelling the shortest total distance. Distances between all pairs are known.",
    "We run 3 machines over the next 4 weeks. Each week we decide how many units of 2 products "
    "to make, with inventory carried between weeks at a holding cost of 2 per unit per week.",
    "Choose the price of our product to maximize revenue, where demand falls as 1000 - 20 * price "
    "and revenue is price times demand.",
]


def _money(domain: dict[str, Any], value: float, rng: random.Random) -> str:
    if rng.random() < 0.5:
        return f"{domain['money']}{value:,.0f}"
    return f"{value:,.0f}"


# --------------------------------------------------------------------------- transportation


def _transport_spec(
    rng: random.Random, domain: dict[str, Any]
) -> tuple[TransportationProblem, list[str]]:
    while True:
        n_src, n_dst = rng.randint(2, 3), rng.randint(2, 4)
        srcs = rng.sample(domain["srcs"], n_src)
        dsts = rng.sample(domain["dsts"], n_dst)
        scale = rng.choice([1, 10, 100])
        demand = {d: rng.randint(2, 9) * 5 * scale for d in dsts}
        total = sum(demand.values())
        surplus = rng.choice([0, 0, rng.randint(1, 4) * 5 * scale])
        weights = [rng.randint(2, 6) for _ in srcs]
        supply = {s: total * w // sum(weights) for s, w in zip(srcs, weights, strict=True)}
        supply[srcs[0]] += total + surplus - sum(supply.values())

        features: list[str] = []
        routes = {(s, d): rng.randint(2, 30) for s in srcs for d in dsts}
        if rng.random() < 0.4:
            routes.pop(rng.choice(list(routes)))
            features.append("blocked_route")
        caps: dict[tuple[str, str], int] = {}
        if rng.random() < 0.35:
            key = rng.choice(list(routes))
            caps[key] = max(5, demand[key[1]] // 2 // 5 * 5)
            features.append("route_capacity")
        at_least = rng.random() < 0.25
        if at_least:
            features.append("at_least_demand")
        if surplus:
            features.append("excess_supply")

        problem = TransportationProblem(
            name=f"{domain['src'].title()} to {domain['dst']} shipping",
            sources=[Source(id=s, supply=supply[s]) for s in srcs],
            destinations=[Destination(id=d, demand=demand[d]) for d in dsts],
            routes=[
                Route(source=s, destination=d, cost=c, capacity=caps.get((s, d)))
                for (s, d), c in routes.items()
            ],
            demand_constraint="at_least" if at_least else "equal",
        )
        if solve_problem(problem).result.status == SolveStatus.OPTIMAL:
            return problem, features


def _transport_text(
    p: TransportationProblem, domain: dict[str, Any], style: str, rng: random.Random
) -> str:
    unit, src, dst = domain["unit"], domain["src"], domain["dst"]
    cost = {(r.source, r.destination): r.cost for r in p.routes}
    caps = [r for r in p.routes if r.capacity is not None]
    all_pairs = [(s.id, d.id) for s in p.sources for d in p.destinations]
    blocked = [k for k in all_pairs if k not in cost]
    need = "at least" if p.demand_constraint == "at_least" else ""

    if style == "list":
        lines = [f"We ship {unit} from {len(p.sources)} {src}s to {len(p.destinations)} {dst}s."]
        lines.append(
            "Supply: " + "; ".join(f"{s.id} has {s.supply:,.0f} {unit}" for s in p.sources) + "."
        )
        lines.append(
            "Demand: "
            + "; ".join(
                f"{d.id} needs {need + ' ' if need else ''}{d.demand:,.0f} {unit}"
                for d in p.destinations
            )
            + "."
        )
        lines.append(
            f"Cost per {unit[:-1]}: "
            + "; ".join(f"{s} to {d} costs {_money(domain, c, rng)}" for (s, d), c in cost.items())
            + "."
        )
    elif style == "narrative":
        lines = []
        for s in p.sources:
            parts = [
                f"{d} at {_money(domain, cost[(s.id, d)], rng)} per {unit[:-1]}"
                for d in (x.id for x in p.destinations)
                if (s.id, d) in cost
            ]
            lines.append(
                f"The {src} in {s.id} can send up to {s.supply:,.0f} {unit}, shipping to "
                + ", ".join(parts)
                + "."
            )
        for d in p.destinations:
            lines.append(f"{d.id} requires {need + ' ' if need else ''}{d.demand:,.0f} {unit}.")
    else:  # table
        header = "| from \\ to | " + " | ".join(d.id for d in p.destinations) + " | supply |"
        rows = [
            f"| {s.id} | "
            + " | ".join(
                f"{cost[(s.id, d.id)]:,.0f}" if (s.id, d.id) in cost else "-"
                for d in p.destinations
            )
            + f" | {s.supply:,.0f} |"
            for s in p.sources
        ]
        demand_row = "| demand | " + " | ".join(f"{d.demand:,.0f}" for d in p.destinations) + " | |"
        lines = [
            f"Unit shipping costs from each {src} to each {dst} ({unit}):",
            header,
            *rows,
            demand_row,
        ]
        if need:
            lines.append(f"Each {dst} must receive at least its demand.")

    if blocked:
        if style == "table":
            lines.append(f"A dash means the {src} cannot ship to that {dst}.")
        else:
            lines += [f"{s} cannot ship to {d}." for s, d in blocked]
    lines += [
        f"At most {r.capacity:,.0f} {unit} can go from {r.source} to {r.destination}." for r in caps
    ]
    lines.append("Find the shipping plan with the lowest total cost.")
    return "\n".join(lines) if style == "table" else " ".join(lines)


# --------------------------------------------------------------------------- assignment


def _assign_spec(rng: random.Random, domain: dict[str, Any]) -> tuple[AssignmentProblem, list[str]]:
    while True:
        features: list[str] = []
        n_tasks = rng.randint(3, 4)
        tasks = rng.sample(domain["tasks"], n_tasks)
        required = {t: 1 for t in tasks}
        if rng.random() < 0.3:
            required[rng.choice(tasks)] = 2
            features.append("task_needs_two")
        capacity_two = rng.random() < 0.25
        n_agents = sum(required.values()) + rng.choice([0, 1])
        n_agents = min(n_agents, len(domain["agents"]))
        agents = rng.sample(domain["agents"], n_agents)
        capacity = {a: 1 for a in agents}
        if capacity_two:
            capacity[rng.choice(agents)] = 2
            features.append("agent_takes_two")
        hi = 10 if domain["sense"] == "maximize" else 60
        pairs = {(a, t): rng.randint(1, hi) for a in agents for t in tasks}
        if rng.random() < 0.4:
            pairs.pop(rng.choice(list(pairs)))
            features.append("forbidden_pair")
        if n_agents > sum(required.values()):
            features.append("spare_agent")
        problem = AssignmentProblem(
            name=f"Assign {domain['agent']}s to {domain['task']}s",
            sense=domain["sense"],
            agents=[Agent(id=a, capacity=capacity[a]) for a in agents],
            tasks=[Task(id=t, required=required[t]) for t in tasks],
            pairings=[Pairing(agent=a, task=t, value=v) for (a, t), v in pairs.items()],
        )
        if solve_problem(problem).result.status == SolveStatus.OPTIMAL:
            return problem, features


def _assign_text(p: AssignmentProblem, domain: dict[str, Any], style: str) -> str:
    agent, task, value = domain["agent"], domain["task"], domain["value"]
    vals = {(x.agent, x.task): x.value for x in p.pairings}
    goal = "maximizes the total" if p.sense == "maximize" else "minimizes the total"
    lines: list[str] = []

    if style == "table":
        lines.append(f"{value.capitalize()} for each {agent} (rows) and {task} (columns):")
        lines.append("| | " + " | ".join(t.id for t in p.tasks) + " |")
        lines += [
            f"| {a.id} | "
            + " | ".join(
                f"{vals[(a.id, t.id)]:g}" if (a.id, t.id) in vals else "-" for t in p.tasks
            )
            + " |"
            for a in p.agents
        ]
        if len(vals) < len(p.agents) * len(p.tasks):
            lines.append("A dash means that pairing is not allowed.")
    else:
        for a in p.agents:
            parts = [f"{t.id} {vals[(a.id, t.id)]:g}" for t in p.tasks if (a.id, t.id) in vals]
            lines.append(f"{a.id}'s {value} by {task}: " + ", ".join(parts) + ".")
        for a in p.agents:
            missing = [t.id for t in p.tasks if (a.id, t.id) not in vals]
            lines += [f"{a.id} cannot be assigned to {t}." for t in missing]

    lines += [f"{t.id} needs two {agent}s." for t in p.tasks if t.required == 2]
    if all(t.required == 1 for t in p.tasks):
        lines.append(f"Each {task} needs exactly one {agent}.")
    else:
        lines.append(f"Every other {task} needs exactly one {agent}.")
    lines += [f"{a.id} can take two {task}s." for a in p.agents if a.capacity == 2]
    lines.append(
        f"{'Every other' if any(a.capacity == 2 for a in p.agents) else 'Each'} {agent} "
        f"can take at most one {task}."
    )
    lines.append(f"Find the assignment that {goal} {value}.")
    return "\n".join(lines) if style == "table" else " ".join(lines)


# --------------------------------------------------------------------------- build


def generate(n_transport: int = 12, n_assign: int = 12, seed: int = SEED) -> list[Item]:
    rng = random.Random(seed)
    items: list[Item] = []
    styles = ["list", "narrative", "table"]
    for i in range(n_transport):
        domain = TRANSPORT_DOMAINS[i % len(TRANSPORT_DOMAINS)]
        style = styles[i % len(styles)]
        problem, features = _transport_spec(rng, domain)
        items.append(
            Item(
                id=f"T{i + 1:02d}",
                kind="transportation",
                style=style,
                features=features,
                text=_transport_text(problem, domain, style, rng),
                problem=problem,
                expected_objective=solve_problem(problem).result.objective,
            )
        )
    for i in range(n_assign):
        domain = ASSIGN_DOMAINS[i % len(ASSIGN_DOMAINS)]
        style = ["sentences", "table"][i % 2]
        assignment, features = _assign_spec(rng, domain)
        items.append(
            Item(
                id=f"A{i + 1:02d}",
                kind="assignment",
                style=style,
                features=features,
                text=_assign_text(assignment, domain, style),
                problem=assignment,
                expected_objective=solve_problem(assignment).result.objective,
            )
        )
    items += [
        Item(id=f"U{i + 1:02d}", kind="unsupported", style="prose", features=[], text=text)
        for i, text in enumerate(UNSUPPORTED)
    ]
    return items


def write(path: Path, items: list[Item]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(item.model_dump_json() + "\n")


def load(path: Path) -> list[Item]:
    return [
        Item.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / f"{DATASET}.jsonl"

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    items = generate()
    write(out, items)
    counts = {
        k: sum(i.kind == k for i in items) for k in ("transportation", "assignment", "unsupported")
    }
    print(f"wrote {len(items)} problems to {out}: {json.dumps(counts)}")

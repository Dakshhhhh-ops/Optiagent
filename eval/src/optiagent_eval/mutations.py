"""Inject realistic modelling errors into correct problems, then measure what the audit catches.

uv run python -m optiagent_eval.mutations
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ValidationError

from optiagent_agent.audit import audit
from optiagent_core.schema import AssignmentProblem, Pairing, Route, TransportationProblem
from optiagent_eval.generate import DEFAULT_PATH, load

Problem = TransportationProblem | AssignmentProblem
RESULTS = Path(__file__).resolve().parents[2] / "results" / "audit_mutations_v1.json"


def _nudge(value: float, rng: random.Random) -> float:
    return (
        value + rng.choice([-3, -2, -1, 1, 2, 3, 5]) if value > 3 else value + rng.choice([1, 2, 5])
    )


def _transport_mutants(p: TransportationProblem, rng: random.Random) -> dict[str, Problem]:
    out: dict[str, Problem] = {}
    routes = list(p.routes)
    i = rng.randrange(len(routes))
    r = routes[i]

    out["wrong_cost"] = p.model_copy(
        update={
            "routes": [
                *routes[:i],
                r.model_copy(update={"cost": _nudge(r.cost, rng)}),
                *routes[i + 1 :],
            ]
        }
    )
    out["unit_scale"] = p.model_copy(
        update={
            "routes": [*routes[:i], r.model_copy(update={"cost": r.cost * 1000}), *routes[i + 1 :]]
        }
    )
    if len(routes) > 1:
        out["missing_route"] = p.model_copy(update={"routes": routes[:i] + routes[i + 1 :]})
    same_source = [k for k, x in enumerate(routes) if x.source == r.source and x.cost != r.cost]
    if same_source:
        k = same_source[0]
        swapped = list(routes)
        swapped[i] = r.model_copy(update={"cost": routes[k].cost})
        swapped[k] = routes[k].model_copy(update={"cost": r.cost})
        out["swapped_values"] = p.model_copy(update={"routes": swapped})

    present = {(x.source, x.destination) for x in routes}
    blocked = [
        (s.id, d.id) for s in p.sources for d in p.destinations if (s.id, d.id) not in present
    ]
    if blocked:
        s, d = blocked[0]
        out["extra_route"] = p.model_copy(
            update={"routes": [*routes, Route(source=s, destination=d, cost=rng.randint(2, 30))]}
        )

    src = rng.randrange(len(p.sources))
    out["wrong_supply"] = p.model_copy(
        update={"sources": [s.model_copy(update={"supply": s.supply + 10}) if k == src else s
                            for k, s in enumerate(p.sources)]}
    )  # fmt: skip
    dst = rng.randrange(len(p.destinations))
    out["wrong_demand"] = p.model_copy(
        update={"destinations": [d.model_copy(update={"demand": d.demand + 5}) if k == dst else d
                                 for k, d in enumerate(p.destinations)]}
    )  # fmt: skip
    out["flipped_sense"] = p.model_copy(update={"sense": "maximize"})
    out["flipped_demand_direction"] = p.model_copy(
        update={"demand_constraint": "equal" if p.demand_constraint == "at_least" else "at_least"}
    )

    capped = [k for k, x in enumerate(routes) if x.capacity is not None]
    if capped:
        k = capped[0]
        out["missing_capacity"] = p.model_copy(
            update={
                "routes": [
                    x.model_copy(update={"capacity": None}) if j == k else x
                    for j, x in enumerate(routes)
                ]
            }
        )
    uncapped = [k for k, x in enumerate(routes) if x.capacity is None]
    if uncapped:
        k = uncapped[0]
        out["extra_capacity"] = p.model_copy(
            update={
                "routes": [
                    x.model_copy(update={"capacity": 10.0}) if j == k else x
                    for j, x in enumerate(routes)
                ]
            }
        )
    return out


def _assign_mutants(p: AssignmentProblem, rng: random.Random) -> dict[str, Problem]:
    out: dict[str, Problem] = {}
    pairs = list(p.pairings)
    i = rng.randrange(len(pairs))
    x = pairs[i]
    out["wrong_value"] = p.model_copy(
        update={
            "pairings": [
                *pairs[:i],
                x.model_copy(update={"value": _nudge(x.value, rng)}),
                *pairs[i + 1 :],
            ]
        }
    )
    out["unit_scale"] = p.model_copy(
        update={
            "pairings": [
                *pairs[:i],
                x.model_copy(update={"value": x.value * 1000}),
                *pairs[i + 1 :],
            ]
        }
    )
    out["missing_pair"] = p.model_copy(update={"pairings": pairs[:i] + pairs[i + 1 :]})
    same_agent = [k for k, y in enumerate(pairs) if y.agent == x.agent and y.value != x.value]
    if same_agent:
        k = same_agent[0]
        swapped = list(pairs)
        swapped[i] = x.model_copy(update={"value": pairs[k].value})
        swapped[k] = pairs[k].model_copy(update={"value": x.value})
        out["swapped_values"] = p.model_copy(update={"pairings": swapped})
    present = {(y.agent, y.task) for y in pairs}
    forbidden = [(a.id, t.id) for a in p.agents for t in p.tasks if (a.id, t.id) not in present]
    if forbidden:
        a, t = forbidden[0]
        out["extra_pair"] = p.model_copy(
            update={"pairings": [*pairs, Pairing(agent=a, task=t, value=5)]}
        )
    out["flipped_sense"] = p.model_copy(
        update={"sense": "minimize" if p.sense == "maximize" else "maximize"}
    )
    ti = rng.randrange(len(p.tasks))
    out["wrong_required"] = p.model_copy(
        update={"tasks": [y.model_copy(update={"required": 2 if y.required == 1 else 1}) if k == ti else y
                          for k, y in enumerate(p.tasks)]}
    )  # fmt: skip
    ai = rng.randrange(len(p.agents))
    out["wrong_capacity"] = p.model_copy(
        update={"agents": [y.model_copy(update={"capacity": 2 if y.capacity == 1 else 1}) if k == ai else y
                           for k, y in enumerate(p.agents)]}
    )  # fmt: skip
    return out


def mutants(problem: Problem, rng: random.Random) -> dict[str, Problem]:
    built = (
        _transport_mutants(problem, rng)
        if isinstance(problem, TransportationProblem)
        else _assign_mutants(problem, rng)
    )
    valid: dict[str, Problem] = {}
    for name, m in built.items():
        try:
            valid[name] = type(m).model_validate(m.model_dump())
        except ValidationError:
            continue
    return valid


class CategoryResult(BaseModel):
    category: str
    injected: int
    detected: int

    @property
    def rate(self) -> float:
        return self.detected / self.injected if self.injected else 0.0


class AuditEval(BaseModel):
    problems: int
    false_alarms: int
    injected: int
    detected: int
    categories: list[CategoryResult]
    missed: list[str]


def evaluate(seed: int = 7) -> AuditEval:
    rng = random.Random(seed)
    items = [i for i in load(DEFAULT_PATH) if i.problem is not None]
    false_alarms = sum(
        any(f.severity != "info" for f in audit(i.problem, i.text).findings)  # type: ignore[arg-type]
        for i in items
    )
    injected: dict[str, int] = defaultdict(int)
    detected: dict[str, int] = defaultdict(int)
    missed: list[str] = []
    for item in items:
        assert item.problem is not None
        for category, mutant in mutants(item.problem, rng).items():
            injected[category] += 1
            if any(f.severity != "info" for f in audit(mutant, item.text).findings):
                detected[category] += 1
            else:
                missed.append(f"{item.id}:{category}")
    categories = [
        CategoryResult(category=c, injected=n, detected=detected[c])
        for c, n in sorted(injected.items())
    ]
    return AuditEval(
        problems=len(items),
        false_alarms=false_alarms,
        injected=sum(injected.values()),
        detected=sum(detected.values()),
        categories=categories,
        missed=missed,
    )


if __name__ == "__main__":
    result = evaluate()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"false alarms on correct models: {result.false_alarms}/{result.problems}")
    print(f"injected errors detected: {result.detected}/{result.injected} "
          f"({result.detected / result.injected:.0%})\n")  # fmt: skip
    for c in result.categories:
        print(f"  {c.category:<26} {c.detected:>3}/{c.injected:<3} {c.rate:6.0%}")
    if result.missed:
        print("\nmissed:", ", ".join(result.missed))
    print(f"\nwrote {RESULTS}")
    print(json.dumps({"detection_rate": round(result.detected / result.injected, 3)}))

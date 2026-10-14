"""Held-out, hand-written problems in free prose.

Unlike the generated set, these were written by hand in phrasings the audit's text patterns
were not developed on (decimals, currency signs, arrows, "rates them 4 and 8", numbers before
the pair they belong to, British spelling). They test how the audit and the LLM generalise.

    uv run python -m optiagent_eval.handwritten     # writes eval/data/handwritten_v1.jsonl
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem
from optiagent_eval.generate import Item, write

PATH = Path(__file__).resolve().parents[2] / "data" / "handwritten_v1.jsonl"


def _t(sources: dict[str, float], dests: dict[str, float], costs: dict[tuple[str, str], float],
       caps: dict[tuple[str, str], float] | None = None, **kw: Any) -> TransportationProblem:  # fmt: skip
    caps = caps or {}
    return TransportationProblem.model_validate(
        {
            "sources": [{"id": k, "supply": v} for k, v in sources.items()],
            "destinations": [{"id": k, "demand": v} for k, v in dests.items()],
            "routes": [
                {"source": s, "destination": d, "cost": c, "capacity": caps.get((s, d))}
                for (s, d), c in costs.items()
            ],
            **kw,
        }
    )


def _a(values: dict[tuple[str, str], float], capacity: dict[str, int] | None = None,
       required: dict[str, int] | None = None, **kw: Any) -> AssignmentProblem:  # fmt: skip
    agents = list(dict.fromkeys(a for a, _ in values))
    tasks = list(dict.fromkeys(t for _, t in values))
    capacity, required = capacity or {}, required or {}
    return AssignmentProblem.model_validate(
        {
            "agents": [{"id": a, "capacity": capacity.get(a, 1)} for a in agents],
            "tasks": [{"id": t, "required": required.get(t, 1)} for t in tasks],
            "pairings": [{"agent": a, "task": t, "value": v} for (a, t), v in values.items()],
            **kw,
        }
    )


CASES: list[tuple[str, str, TransportationProblem | AssignmentProblem]] = [
    (
        "H01",
        "Our two bakeries supply three cafés every morning. The Riverside bakery can bake up to "
        "120 loaves and the Hilltop bakery up to 80. Café Blue wants 70 loaves, Café Green 60 and "
        "Café Rose 50. Delivering a loaf from Riverside costs 0.40 to Café Blue, 0.55 to Café "
        "Green and 0.70 to Café Rose; from Hilltop it costs 0.65 to Café Blue, 0.35 to Café Green "
        "and 0.45 to Café Rose. Plan deliveries to keep the delivery bill as small as possible.",
        _t(
            {"Riverside": 120, "Hilltop": 80},
            {"Café Blue": 70, "Café Green": 60, "Café Rose": 50},
            {
                ("Riverside", "Café Blue"): 0.40,
                ("Riverside", "Café Green"): 0.55,
                ("Riverside", "Café Rose"): 0.70,
                ("Hilltop", "Café Blue"): 0.65,
                ("Hilltop", "Café Green"): 0.35,
                ("Hilltop", "Café Rose"): 0.45,
            },
        ),
    ),
    (
        "H02",
        "Three plants (Leeds, Bristol and Glasgow) make pallets for four depots: North, South, "
        "East and West. Leeds can produce 1,500 pallets, Bristol 1,200 and Glasgow 900. Each depot "
        "must receive at least its order: North 800, South 1,100, East 700 and West 600. Shipping "
        "costs per pallet are Leeds→North £4, Leeds→South £7, Leeds→East £6, Leeds→West £8; "
        "Bristol→North £9, Bristol→South £3, Bristol→East £5, Bristol→West £4; Glasgow→North £2, "
        "Glasgow→South £10, Glasgow→East £8. Glasgow has no route to West. The lane from Bristol "
        "to South can carry at most 900 pallets. What is the cheapest plan?",
        _t(
            {"Leeds": 1500, "Bristol": 1200, "Glasgow": 900},
            {"North": 800, "South": 1100, "East": 700, "West": 600},
            {
                ("Leeds", "North"): 4,
                ("Leeds", "South"): 7,
                ("Leeds", "East"): 6,
                ("Leeds", "West"): 8,
                ("Bristol", "North"): 9,
                ("Bristol", "South"): 3,
                ("Bristol", "East"): 5,
                ("Bristol", "West"): 4,
                ("Glasgow", "North"): 2,
                ("Glasgow", "South"): 10,
                ("Glasgow", "East"): 8,
            },
            caps={("Bristol", "South"): 900},
            demand_constraint="at_least",
        ),
    ),
    (
        "H03",
        "We have four machines and four jobs. Machine M1 takes 14 minutes for job J1, 5 for J2, 8 "
        "for J3 and 7 for J4. M2 takes 2, 12, 6 and 5 minutes for J1 to J4. M3 takes 7, 8, 3 and "
        "9. M4 takes 2, 4, 6 and 10. Each machine does one job and each job goes to one machine. "
        "Minimise the total processing time.",
        _a(
            {
                ("M1", "J1"): 14,
                ("M1", "J2"): 5,
                ("M1", "J3"): 8,
                ("M1", "J4"): 7,
                ("M2", "J1"): 2,
                ("M2", "J2"): 12,
                ("M2", "J3"): 6,
                ("M2", "J4"): 5,
                ("M3", "J1"): 7,
                ("M3", "J2"): 8,
                ("M3", "J3"): 3,
                ("M3", "J4"): 9,
                ("M4", "J1"): 2,
                ("M4", "J2"): 4,
                ("M4", "J3"): 6,
                ("M4", "J4"): 10,
            },
        ),
    ),
    (
        "H04",
        "Three volunteers, Ana, Ben and Chloe, sign up for two stalls at the fair: the book stall "
        "and the food stall. The food stall needs two people and the book stall needs one. Ana "
        "rates the book stall 9 and the food stall 6; Ben rates them 4 and 8; Chloe rates them 7 "
        "and 7. Everyone works one stall. Maximise the total rating.",
        _a(
            {
                ("Ana", "book stall"): 9,
                ("Ana", "food stall"): 6,
                ("Ben", "book stall"): 4,
                ("Ben", "food stall"): 8,
                ("Chloe", "book stall"): 7,
                ("Chloe", "food stall"): 7,
            },
            required={"food stall": 2},
            sense="maximize",
        ),
    ),
    (
        "H05",
        "A cooperative sells apples from two orchards, North Orchard (300 crates) and South "
        "Orchard (250 crates), to three shops. Shop A will take exactly 200 crates, Shop B exactly "
        "150 and Shop C exactly 120. The profit per crate is 5 from North Orchard to Shop A, 6 to "
        "Shop B and 4 to Shop C; from South Orchard it is 7 to Shop A, 3 to Shop B and 5 to Shop "
        "C. Choose shipments that maximise total profit.",
        _t(
            {"North Orchard": 300, "South Orchard": 250},
            {"Shop A": 200, "Shop B": 150, "Shop C": 120},
            {
                ("North Orchard", "Shop A"): 5,
                ("North Orchard", "Shop B"): 6,
                ("North Orchard", "Shop C"): 4,
                ("South Orchard", "Shop A"): 7,
                ("South Orchard", "Shop B"): 3,
                ("South Orchard", "Shop C"): 5,
            },
            sense="maximize",
        ),
    ),
    (
        "H06",
        "Two warehouses serve two hospitals with oxygen cylinders. Warehouse East holds 60 "
        "cylinders and Warehouse West holds 45. Mercy Hospital needs 50 and General Hospital "
        "needs 40. It costs $12 to move a cylinder from Warehouse East to Mercy Hospital and $20 "
        "to General Hospital. From Warehouse West the cost is $18 to Mercy Hospital and $9 to "
        "General Hospital. No more than 30 cylinders may travel from Warehouse West to General "
        "Hospital. Minimize the transport cost.",
        _t(
            {"Warehouse East": 60, "Warehouse West": 45},
            {"Mercy Hospital": 50, "General Hospital": 40},
            {
                ("Warehouse East", "Mercy Hospital"): 12,
                ("Warehouse East", "General Hospital"): 20,
                ("Warehouse West", "Mercy Hospital"): 18,
                ("Warehouse West", "General Hospital"): 9,
            },
            caps={("Warehouse West", "General Hospital"): 30},
        ),
    ),
    (
        "H07",
        "Assign three interns to three projects so the total learning score is as high as "
        "possible. Priya would score 6 on Search, 9 on Payments and 4 on Mobile. Tom would score 8 "
        "on Search, 5 on Payments and 7 on Mobile. Wei would score 5 on Search, 6 on Payments and "
        "9 on Mobile. Every intern gets exactly one project and every project gets one intern.",
        _a(
            {
                ("Priya", "Search"): 6,
                ("Priya", "Payments"): 9,
                ("Priya", "Mobile"): 4,
                ("Tom", "Search"): 8,
                ("Tom", "Payments"): 5,
                ("Tom", "Mobile"): 7,
                ("Wei", "Search"): 5,
                ("Wei", "Payments"): 6,
                ("Wei", "Mobile"): 9,
            },
            sense="maximize",
        ),
    ),
    (
        "H08",
        "Four couriers cover three delivery zones. Zone Central needs two couriers; Zone Harbour "
        "and Zone Airport need one each. Each courier covers at most one zone. Daily cost in "
        "rupees: Arjun costs 900 in Zone Central, 1,100 in Zone Harbour and 1,300 in Zone "
        "Airport. Bela costs 950 in Zone Central and 1,000 in Zone Harbour; Bela cannot work in "
        "Zone Airport. Chen costs 1,200 in Zone Central, 1,150 in Zone Harbour and 1,000 in Zone "
        "Airport. Dev costs 1,000 in Zone Central, 1,250 in Zone Harbour and 1,100 in Zone "
        "Airport. Keep the total daily cost as low as possible.",
        _a(
            {
                ("Arjun", "Zone Central"): 900,
                ("Arjun", "Zone Harbour"): 1100,
                ("Arjun", "Zone Airport"): 1300,
                ("Bela", "Zone Central"): 950,
                ("Bela", "Zone Harbour"): 1000,
                ("Chen", "Zone Central"): 1200,
                ("Chen", "Zone Harbour"): 1150,
                ("Chen", "Zone Airport"): 1000,
                ("Dev", "Zone Central"): 1000,
                ("Dev", "Zone Harbour"): 1250,
                ("Dev", "Zone Airport"): 1100,
            },
            required={"Zone Central": 2},
        ),
    ),
]


def items() -> list[Item]:
    out = []
    for ident, text, problem in CASES:
        report = solve_problem(problem)
        assert report.verified, ident
        out.append(
            Item(
                id=ident,
                kind=problem.kind,
                style="handwritten",
                features=[],
                text=text,
                problem=problem,
                expected_objective=report.result.objective,
            )
        )
    return out


if __name__ == "__main__":
    data = items()
    write(PATH, data)
    for i in data:
        print(f"{i.id} {i.kind:<14} optimum={i.expected_objective:g}")
    print(f"wrote {len(data)} problems to {PATH}")

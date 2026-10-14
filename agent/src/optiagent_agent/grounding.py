"""Number grounding: every number in an extracted problem must appear in the user's text.

This catches the most damaging LLM failure, a plausible value that was never given.
It is deterministic and cheap, so it runs on every text extraction.
"""

from __future__ import annotations

import math
import re

from pydantic import BaseModel

from optiagent_core.schema import AssignmentProblem, TransportationProblem

_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w])")
_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "single": 1, "both": 2, "pair": 2, "dozen": 12,
}  # fmt: skip


class Ungrounded(BaseModel):
    field: str
    value: float


def numbers_in(text: str) -> set[float]:
    found = {float(m.group().replace(",", "")) for m in _NUMBER.finditer(text)}
    words = re.findall(r"[a-z]+", text.lower())
    found |= {float(_WORDS[w]) for w in words if w in _WORDS}
    return found


def _present(value: float, numbers: set[float]) -> bool:
    return any(math.isclose(value, n, rel_tol=1e-9, abs_tol=1e-9) for n in numbers)


def ungrounded_values(
    problem: TransportationProblem | AssignmentProblem, text: str
) -> list[Ungrounded]:
    numbers = numbers_in(text)
    values: list[tuple[str, float]] = []
    if isinstance(problem, TransportationProblem):
        values += [(f"supply of {s.id}", s.supply) for s in problem.sources]
        values += [(f"demand of {d.id}", d.demand) for d in problem.destinations]
        for r in problem.routes:
            values.append((f"cost {r.source} → {r.destination}", r.cost))
            if r.capacity is not None:
                values.append((f"capacity {r.source} → {r.destination}", r.capacity))
    else:
        values += [(f"value {p.agent} → {p.task}", p.value) for p in problem.pairings]
        # A capacity or requirement of 1 is the default and is usually implied, not stated.
        values += [(f"capacity of {a.id}", a.capacity) for a in problem.agents if a.capacity != 1]
        values += [
            (f"agents needed for {t.id}", t.required) for t in problem.tasks if t.required != 1
        ]
    return [Ungrounded(field=f, value=v) for f, v in values if not _present(v, numbers)]

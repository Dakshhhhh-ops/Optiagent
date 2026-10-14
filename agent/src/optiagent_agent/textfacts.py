"""Read checkable facts out of the user's text, anchored on the ids in an extracted problem.

This is deliberately conservative: a fact is only recorded when the text pattern is
unambiguous (one source/agent in the clause, a number right after a destination/task, ...).
Missing a fact costs nothing; a wrong fact would cause a false alarm in the audit.
"""

from __future__ import annotations

import re
from itertools import pairwise
from collections.abc import Iterator

from pydantic import BaseModel, Field

from optiagent_core.schema import AssignmentProblem, TransportationProblem

_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "single": 1,
}  # fmt: skip
_NUM = re.compile(
    r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w])|\b(?:"
    + "|".join(_WORDS)
    + r")\b",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"\.(?!\d)|(?<!\d)\.|;|\n")  # a period splits unless it is a decimal point
_LIMIT = re.compile(r"\b(at most|no more than|up to|maximum of|max(imum)?|limit(ed)? to)\b", re.I)
_BLOCK = re.compile(
    r"\b(cannot|can't|can not|not allowed|unavailable|no route|not possible|"
    r"must not|may not|never)\b",
    re.I,
)
_AT_LEAST = re.compile(r"\b(at least|no less than|minimum of|or more)\b", re.I)
_MAX_WORDS = re.compile(
    r"\b(maximi[sz](e|es|ed|ing)|highest|largest|most preferred|best total|maximum total)\b",
    re.I,
)
_MIN_WORDS = re.compile(
    r"\b(minimi[sz](e|es|ed|ing)|lowest|cheapest|smallest|least (total )?cost)\b", re.I
)
# "Each lab section needs exactly one TA" / "Every other worker can take at most one job".
_DEFAULT_ONE = re.compile(
    r"\b(each|every)( other)?\s+[\w ]{1,30}?\s+(?P<verb>needs|requires|gets|can take|takes|may take)"
    r"(\s+(exactly|at most|only))?\s+(one|1|a single)\b",
    re.I,
)
_SCALE = re.compile(r"\b(scale|rank|rate|rating|score)s?\b[^.\n]*\bfrom\s+\d+\s+to\s+\d+", re.I)


def _value(token: str) -> float:
    word = token.lower()
    return float(_WORDS[word]) if word in _WORDS else float(token.replace(",", ""))


class Num(BaseModel):
    value: float
    start: int
    end: int


class Mention(BaseModel):
    id: str
    role: str  # "from" | "to"
    start: int
    end: int


class PairFact(BaseModel):
    frm: str
    to: str
    value: float | None
    """None means the text says the pair is not allowed."""
    snippet: str


class EntityFact(BaseModel):
    id: str
    role: str
    value: float
    snippet: str


class Facts(BaseModel):
    pairs: list[PairFact] = Field(default_factory=list)
    limits: list[PairFact] = Field(default_factory=list)
    entities: list[EntityFact] = Field(default_factory=list)
    numbers: list[Num] = Field(default_factory=list)
    wants_max: bool = False
    wants_min: bool = False
    says_at_least: bool = False
    scale_numbers: set[float] = Field(default_factory=set)
    default_one: set[str] = Field(default_factory=set)
    """Roles ("from"/"to") the text says take exactly/at most one unless stated otherwise."""


def numbers(text: str) -> list[Num]:
    return [Num(value=_value(m.group()), start=m.start(), end=m.end()) for m in _NUM.finditer(text)]


def _ids(problem: TransportationProblem | AssignmentProblem) -> tuple[list[str], list[str]]:
    if isinstance(problem, TransportationProblem):
        return [s.id for s in problem.sources], [d.id for d in problem.destinations]
    return [a.id for a in problem.agents], [t.id for t in problem.tasks]


def _mentions(segment: str, froms: list[str], tos: list[str]) -> list[Mention]:
    """Non-overlapping id mentions, longest ids first (so 'L10' wins over 'L1')."""
    found: list[Mention] = []
    taken: list[tuple[int, int]] = []
    candidates = [(i, "from") for i in froms] + [(i, "to") for i in tos]
    for ident, role in sorted(candidates, key=lambda c: -len(c[0])):
        pattern = re.compile(r"(?<![\w])" + re.escape(ident) + r"(?![\w])", re.I)
        for m in pattern.finditer(segment):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append(Mention(id=ident, role=role, start=m.start(), end=m.end()))
    return sorted(found, key=lambda x: x.start)


def _segments(text: str) -> Iterator[str]:
    for line in text.splitlines():
        if line.strip().startswith("|"):
            continue  # tables are parsed separately
        for seg in _SPLIT.split(line):
            if seg.strip():
                yield seg.strip()


def _table_facts(text: str, froms: list[str], tos: list[str], facts: Facts) -> None:
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]
    if len(rows) < 2:
        return
    header, *body = rows
    lower_froms = {f.lower(): f for f in froms}
    lower_tos = {t.lower(): t for t in tos}
    for row in body:
        label = row[0].lower()
        if label in lower_froms:
            frm = lower_froms[label]
            for col, cell in zip(header[1:], row[1:], strict=False):
                key = col.lower()
                nums = numbers(cell)
                if key in lower_tos:
                    blocked = cell.strip() in {"-", "x", "—", "n/a"}
                    if blocked or nums:
                        facts.pairs.append(
                            PairFact(
                                frm=frm,
                                to=lower_tos[key],
                                value=None if blocked else nums[0].value,
                                snippet=f"table row {row[0]}, column {col}",
                            )
                        )
                elif nums and key in {"supply", "capacity", "available"}:
                    facts.entities.append(
                        EntityFact(
                            id=frm, role="from", value=nums[0].value, snippet=f"table row {row[0]}"
                        )
                    )
        elif label in {"demand", "required", "need", "needs"}:
            for col, cell in zip(header[1:], row[1:], strict=False):
                nums = numbers(cell)
                if col.lower() in lower_tos and nums:
                    facts.entities.append(
                        EntityFact(
                            id=lower_tos[col.lower()],
                            role="to",
                            value=nums[0].value,
                            snippet=f"table row {row[0]}",
                        )
                    )


_QUANTITY_WORDS = re.compile(r"\b(needs?|requires?|demands?|wants?|orders?)\b", re.I)


def _clause(seg: str, froms: list[str], tos: list[str], facts: Facts) -> None:
    mentions = _mentions(seg, froms, tos)
    from_mentions = [m for m in mentions if m.role == "from"]
    if len({m.id for m in from_mentions}) > 1:
        # "P1 to C1 is 2, P1 to C2 is 4, P2 to C1 is 3": read each source's part on its own.
        starts = [m.start for m in from_mentions]
        cuts = [0, *starts[1:], len(seg)]
        for a, b in pairwise(cuts):
            _clause(seg[a:b], froms, tos, facts)
        return

    nums = numbers(seg)
    # Numbers inside an id ("Plant 1", "L2") are not values.
    nums = [n for n in nums if not any(m.start <= n.start < m.end for m in mentions)]
    from_ids = {m.id for m in from_mentions}
    to_mentions = [m for m in mentions if m.role == "to"]
    snippet = seg.strip(" ,")

    if _BLOCK.search(seg) and len(from_ids) == 1 and to_mentions:
        frm = next(iter(from_ids))
        facts.pairs += [
            PairFact(frm=frm, to=t.id, value=None, snippet=snippet) for t in to_mentions
        ]
        return

    if _LIMIT.search(seg) and len(from_ids) == 1 and len(to_mentions) == 1 and len(nums) == 1:
        facts.limits.append(
            PairFact(
                frm=next(iter(from_ids)), to=to_mentions[0].id, value=nums[0].value, snippet=snippet
            )
        )
        return

    if len(from_ids) == 1 and to_mentions:
        frm = next(iter(from_ids))
        first_to = to_mentions[0].start
        from_end = from_mentions[0].end
        # A number between the source/agent and its first destination/task is its own value
        # ("Plant B can send up to 30 tons, shipping to ...").
        lead = [n for n in nums if from_end <= n.start < first_to]
        if from_end < first_to and len(lead) == 1:
            facts.entities.append(
                EntityFact(id=frm, role="from", value=lead[0].value, snippet=snippet)
            )
        for t in to_mentions:
            index = mentions.index(t)
            window_end = mentions[index + 1].start if index + 1 < len(mentions) else len(seg)
            after = [n for n in nums if t.end <= n.start < window_end]
            if not after:
                continue
            between = seg[t.end : after[0].start]
            if _QUANTITY_WORDS.search(between):
                # "C1 (needs 25)": the destination's own quantity, not a pair value.
                facts.entities.append(
                    EntityFact(id=t.id, role="to", value=after[0].value, snippet=snippet)
                )
            else:
                facts.pairs.append(
                    PairFact(frm=frm, to=t.id, value=after[0].value, snippet=snippet)
                )
        return

    if len(mentions) == 1 and nums:
        m = mentions[0]
        after = [n for n in nums if n.start >= m.end] or nums
        facts.entities.append(
            EntityFact(id=m.id, role=m.role, value=after[0].value, snippet=snippet)
        )
    elif mentions and len({m.role for m in mentions}) == 1:
        # A list of one kind of entity, each followed by its own number:
        # "Austin requires 20 tons, Seattle 20 tons and Denver 30 tons".
        for k, m in enumerate(mentions):
            end = mentions[k + 1].start if k + 1 < len(mentions) else len(seg)
            own = [n for n in nums if m.end <= n.start < end]
            if own:
                facts.entities.append(
                    EntityFact(id=m.id, role=m.role, value=own[0].value, snippet=snippet)
                )


def extract_facts(text: str, problem: TransportationProblem | AssignmentProblem) -> Facts:
    froms, tos = _ids(problem)
    facts = Facts(
        numbers=numbers(text),
        wants_max=bool(_MAX_WORDS.search(text)),
        wants_min=bool(_MIN_WORDS.search(text)),
        says_at_least=bool(_AT_LEAST.search(text)),
    )
    for match in _DEFAULT_ONE.finditer(text):
        verb = match.group("verb").lower()
        facts.default_one.add("to" if verb in {"needs", "requires", "gets"} else "from")
    for match in _SCALE.finditer(text):
        facts.scale_numbers |= {n.value for n in numbers(match.group())[-2:]}
    _table_facts(text, froms, tos, facts)

    for seg in _segments(text):
        _clause(seg, froms, tos, facts)
    return facts

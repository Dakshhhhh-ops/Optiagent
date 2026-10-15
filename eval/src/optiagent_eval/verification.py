"""Deterministic verification benchmark: which checks catch which errors, at what false-alarm rate.

uv run python -m optiagent_eval.verification

Four parts, none of which call an LLM:

1. Formulation errors. Correct models from the generated and hand-written sets are mutated one
   error at a time (eval/mutations.py). Each detector must flag the mutant and must not flag the
   correct model. Detectors: the formulation audit, requirement traceability, and both together.
   Two reference baselines bound the metrics: "no verification" never flags anything and
   "flag everything" flags every model (perfect recall, useless precision).
2. Builder faults. The model built from a correct problem is corrupted (a dropped row, a flipped
   inequality, a wrong coefficient...) as a buggy model builder would. A fault is harmful when
   the plan solved from the corrupted model violates the problem data or is not optimal for it.
   Layer 1 checks the plan against the (corrupted) model; the problem-level checks read the data.
3. Malformed data. Sample datasets are corrupted cell by cell; the loader must report an error.
4. Scope. Short requests labelled supported / unsupported; the unsupported-semantics detector
   must flag the unsupported ones only.

Rates come with 95% Wilson intervals. Samples are small, so treat them as indicative.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from optiagent_agent.audit import audit
from optiagent_agent.traceability import trace, unsupported_statements
from optiagent_core.builders import build_model
from optiagent_core.checks import verify_solution
from optiagent_core.ingest import load_problem, read_file
from optiagent_core.ingest.suggest import suggest_mapping
from optiagent_core.model import LinearModel, Sense
from optiagent_core.plancheck import check_plan
from optiagent_core.schema import AssignmentProblem, TransportationProblem
from optiagent_core.solver import SolveStatus, solve
from optiagent_eval.generate import DEFAULT_PATH, Item, load
from optiagent_eval.handwritten import items as handwritten_items
from optiagent_eval.mutations import mutants

Problem = TransportationProblem | AssignmentProblem
ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "verification_v1.json"
SCOPE_TUNING = ROOT / "data" / "scope_v1.jsonl"
"""Used to develop the unsupported-semantics patterns: its scores are optimistic."""
SCOPE_HELD_OUT = ROOT / "data" / "scope_v2.jsonl"
"""Written before the patterns were tuned on scope_v1 and never used for tuning."""
SAMPLES = ROOT.parent / "core" / "src" / "optiagent_core" / "examples" / "datasets"


# --------------------------------------------------------------------------- statistics


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


class Rate(BaseModel):
    k: int
    n: int
    low: float
    high: float

    @property
    def value(self) -> float:
        return self.k / self.n if self.n else 0.0


def rate(k: int, n: int) -> Rate:
    low, high = wilson(k, n)
    return Rate(k=k, n=n, low=round(low, 4), high=round(high, 4))


class DetectorScore(BaseModel):
    detector: str
    recall: Rate
    """Injected errors flagged / injected errors."""
    false_positive_rate: Rate
    """Correct models flagged / correct models."""
    precision: Rate
    """Flagged models that really were wrong / flagged models."""
    by_category: dict[str, Rate]


def score(
    name: str, flags_correct: list[bool], flags_mutant: list[tuple[str, bool]]
) -> DetectorScore:
    tp = sum(f for _, f in flags_mutant)
    fp = sum(flags_correct)
    cats: dict[str, list[bool]] = defaultdict(list)
    for category, flagged in flags_mutant:
        cats[category].append(flagged)
    return DetectorScore(
        detector=name,
        recall=rate(tp, len(flags_mutant)),
        false_positive_rate=rate(fp, len(flags_correct)),
        precision=rate(tp, tp + fp),
        by_category={c: rate(sum(v), len(v)) for c, v in sorted(cats.items())},
    )


# --------------------------------------------------------------------------- 1. formulation errors

Detector = Callable[[Problem, str], bool]

DETECTORS: dict[str, Detector] = {
    "no verification (baseline)": lambda p, t: False,
    "flag everything (baseline)": lambda p, t: True,
    "audit": lambda p, t: any(f.severity != "info" for f in audit(p, t).findings),
    "traceability": lambda p, t: trace(p, t).status != "checked",
}


def _combined(p: Problem, t: str) -> bool:
    return DETECTORS["audit"](p, t) or DETECTORS["traceability"](p, t)


class FormulationResult(BaseModel):
    dataset: str
    problems: int
    mutants: int
    scores: list[DetectorScore]
    missed_by_all: list[str]


def formulation_errors(name: str, items: list[Item], seed: int = 7) -> FormulationResult:
    rng = random.Random(seed)
    items = [i for i in items if i.problem is not None]
    detectors = {**DETECTORS, "audit + traceability": _combined}
    correct: dict[str, list[bool]] = {d: [] for d in detectors}
    mutated: dict[str, list[tuple[str, bool]]] = {d: [] for d in detectors}
    missed = []
    total = 0
    for item in items:
        assert item.problem is not None
        for d, fn in detectors.items():
            correct[d].append(fn(item.problem, item.text))
        for category, mutant in mutants(item.problem, rng).items():
            total += 1
            for d, fn in detectors.items():
                mutated[d].append((category, fn(mutant, item.text)))
            if not mutated["audit + traceability"][-1][1]:
                missed.append(f"{item.id}:{category}")
    return FormulationResult(
        dataset=name,
        problems=len(items),
        mutants=total,
        scores=[score(d, correct[d], mutated[d]) for d in detectors],
        missed_by_all=missed,
    )


# --------------------------------------------------------------------------- 2. builder faults


def _faults(model: LinearModel, rng: random.Random) -> dict[str, LinearModel]:
    out: dict[str, LinearModel] = {}

    def copy() -> LinearModel:
        return model.model_copy(deep=True)

    rows = [k for k, c in enumerate(model.constraints) if c.terms]
    if rows:
        m = copy()
        del m.constraints[rng.choice(rows)]
        out["dropped_constraint"] = m
        m = copy()
        c = m.constraints[rng.choice(rows)]
        flipped: dict[Sense, Sense] = {"<=": ">=", ">=": "<=", "==": "<="}
        c.sense = flipped[c.sense]
        out["flipped_inequality"] = m
        m = copy()
        c = m.constraints[rng.choice(rows)]
        c.rhs = c.rhs * 2 + 1
        out["wrong_rhs"] = m
    m = copy()
    v = m.variables[rng.randrange(len(m.variables))]
    v.objective = -v.objective if v.objective else 7.0
    out["wrong_cost_coefficient"] = m
    m = copy()
    m.sense = "maximize" if m.sense == "minimize" else "minimize"
    out["flipped_objective"] = m
    bounded = [v for v in model.variables if v.ub is not None]
    if bounded:
        m = copy()
        m.variable(rng.choice(bounded).name).ub = None
        out["dropped_bound"] = m
    return out


class FaultResult(BaseModel):
    problems: int
    faults: int
    harmful: int
    """Faults whose plan violates the data or is not optimal for it."""
    model_checks: Rate
    """Layer 1 (against the corrupted model) flags a harmful fault."""
    problem_checks: Rate
    """Problem-level checks (against the data) flag a harmful fault."""
    either: Rate
    false_alarms_on_correct: Rate
    by_fault: dict[str, dict[str, int]]


def builder_faults(items: list[Item], seed: int = 11) -> FaultResult:
    rng = random.Random(seed)
    harmful = model_hits = problem_hits = either = faults = 0
    false_alarms: list[bool] = []
    by_fault: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    problems = [i.problem for i in items if i.problem is not None]
    for problem in problems:
        model = build_model(problem)
        base = solve(model)
        if base.status != SolveStatus.OPTIMAL or base.objective is None:
            continue
        clean = check_plan(problem, base.values, base.objective, duals=base.duals)
        false_alarms.append(
            not verify_solution(model, base).passed or not all(c.passed for c in clean)
        )
        for name, faulty in _faults(model, rng).items():
            faults += 1
            result = solve(faulty)
            if not result.has_solution:
                continue  # the fault made it infeasible/unbounded: reported, not a silent error
            # Harmful = the plan breaks the data, or is not optimal for the true model.
            plan_ok = all(c.passed for c in check_plan(problem, result.values, base.objective))
            if plan_ok:
                continue
            harmful += 1
            m = not verify_solution(faulty, result).passed
            p = not all(
                c.passed
                for c in check_plan(problem, result.values, result.objective, duals=result.duals)
            )
            model_hits += m
            problem_hits += p
            either += m or p
            stats = by_fault[name]
            stats["harmful"] += 1
            stats["model_checks"] += m
            stats["problem_checks"] += p
    return FaultResult(
        problems=len(problems),
        faults=faults,
        harmful=harmful,
        model_checks=rate(model_hits, harmful),
        problem_checks=rate(problem_hits, harmful),
        either=rate(either, harmful),
        false_alarms_on_correct=rate(sum(false_alarms), len(false_alarms)),
        by_fault={k: dict(v) for k, v in sorted(by_fault.items())},
    )


# --------------------------------------------------------------------------- 3. malformed data

DATA_FAULTS: dict[str, Callable[[str], str]] = {
    "text_in_number": lambda v: "about ten",
    "nan_cell": lambda v: "nan",
    "infinite_cell": lambda v: "1e999",
    "negative_quantity": lambda v: "-" + v,
    "blank_quantity": lambda v: "",
}


class DataResult(BaseModel):
    datasets: int
    corruptions: int
    detected: Rate
    by_fault: dict[str, Rate]
    clean_false_alarms: Rate
    duplicate_ids: Rate


def _csv_tables(dataset: Path) -> dict[str, list[list[str]]]:
    return {
        f.name: [line.split(",") for line in f.read_text(encoding="utf-8").splitlines()]
        for f in sorted(dataset.glob("*.csv"))
    }


def _load(tables: dict[str, list[list[str]]], kind: str) -> tuple[bool, bool]:
    """(has a problem, has an error) for these tables under the suggested mapping."""
    parsed = [
        t
        for name, rows in tables.items()
        for t in read_file(name, "\n".join(",".join(r) for r in rows).encode())
    ]
    mapping = suggest_mapping(parsed, kind).mapping  # type: ignore[arg-type]
    if mapping is None:
        return False, True
    loaded = load_problem(parsed, mapping)
    return loaded.problem is not None, any(i.severity == "error" for i in loaded.issues)


def malformed_data(seed: int = 5) -> DataResult:
    rng = random.Random(seed)
    datasets = [d for d in sorted(SAMPLES.iterdir()) if d.is_dir() and list(d.glob("*.csv"))]
    hits: dict[str, list[bool]] = defaultdict(list)
    clean: list[bool] = []
    dupes: list[bool] = []
    for d in datasets:
        kind = json.loads((d / "dataset.json").read_text(encoding="utf-8"))["kind"]
        tables = _csv_tables(d)
        ok, err = _load(tables, kind)
        clean.append(err or not ok)
        quantity_tables = [n for n, rows in tables.items() if len(rows[0]) == 2]
        for fault, corrupt in DATA_FAULTS.items():
            if not quantity_tables:
                continue
            name = rng.choice(quantity_tables)
            rows = [list(r) for r in tables[name]]
            r = rng.randrange(1, len(rows))
            rows[r][1] = corrupt(rows[r][1])
            ok, err = _load({**tables, name: rows}, kind)
            hits[fault].append(err or not ok)
        if quantity_tables:
            name = quantity_tables[0]
            rows = [list(r) for r in tables[name]] + [list(tables[name][1])]
            ok, err = _load({**tables, name: rows}, kind)
            dupes.append(err or not ok)
    every = [h for v in hits.values() for h in v]
    return DataResult(
        datasets=len(datasets),
        corruptions=len(every),
        detected=rate(sum(every), len(every)),
        by_fault={k: rate(sum(v), len(v)) for k, v in hits.items()},
        clean_false_alarms=rate(sum(clean), len(clean)),
        duplicate_ids=rate(sum(dupes), len(dupes)),
    )


# --------------------------------------------------------------------------- 4. scope


class ScopeResult(BaseModel):
    dataset: str
    supported: int
    unsupported: int
    recall: Rate
    """Unsupported requests flagged."""
    false_positive_rate: Rate
    """Supported requests wrongly flagged."""
    missed: list[str]
    false_alarms: list[str]


def scope(path: Path) -> ScopeResult:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    flagged = {
        r["id"]: any(x.status == "unsupported" for x in unsupported_statements(r["text"]))
        for r in rows
    }
    bad = [r["id"] for r in rows if r["label"] == "unsupported"]
    good = [r["id"] for r in rows if r["label"] == "supported"]
    return ScopeResult(
        dataset=path.stem,
        supported=len(good),
        unsupported=len(bad),
        recall=rate(sum(flagged[i] for i in bad), len(bad)),
        false_positive_rate=rate(sum(flagged[i] for i in good), len(good)),
        missed=[i for i in bad if not flagged[i]],
        false_alarms=[i for i in good if flagged[i]],
    )


# --------------------------------------------------------------------------- entry point


class VerificationBenchmark(BaseModel):
    formulation: list[FormulationResult]
    builder_faults: FaultResult
    malformed_data: DataResult
    scope_tuning: ScopeResult
    scope_held_out: ScopeResult


def run() -> VerificationBenchmark:
    generated = load(DEFAULT_PATH)
    written = handwritten_items()
    return VerificationBenchmark(
        formulation=[
            formulation_errors("generated (nl_v1)", generated),
            formulation_errors("hand-written (handwritten_v1)", written),
        ],
        builder_faults=builder_faults(generated + written),
        malformed_data=malformed_data(),
        scope_tuning=scope(SCOPE_TUNING),
        scope_held_out=scope(SCOPE_HELD_OUT),
    )


def _pct(r: Rate) -> str:
    return f"{r.value:.0%} ({r.k}/{r.n}, CI {r.low:.0%}–{r.high:.0%})"


if __name__ == "__main__":
    result = run()
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    for f in result.formulation:
        print(f"\n{f.dataset}: {f.problems} correct models, {f.mutants} mutants")
        for s in f.scores:
            print(f"  {s.detector:<28} recall {_pct(s.recall)}  FPR {_pct(s.false_positive_rate)}")
        if f.missed_by_all:
            print("  missed by all:", ", ".join(f.missed_by_all))
    b = result.builder_faults
    print(f"\nbuilder faults: {b.harmful}/{b.faults} harmful")
    print(f"  model checks   {_pct(b.model_checks)}")
    print(f"  problem checks {_pct(b.problem_checks)}")
    print(f"  false alarms on correct plans {_pct(b.false_alarms_on_correct)}")
    d = result.malformed_data
    print(
        f"\nmalformed data: detected {_pct(d.detected)}; clean false alarms {_pct(d.clean_false_alarms)}"
    )
    for sc in (result.scope_tuning, result.scope_held_out):
        print(f"\nscope {sc.dataset}: recall {_pct(sc.recall)}, FPR {_pct(sc.false_positive_rate)}")
        print("  missed:", sc.missed, " false alarms:", sc.false_alarms)
    print(f"\nwrote {RESULTS}")

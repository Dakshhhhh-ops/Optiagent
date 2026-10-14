"""Run the LLM pipeline end to end on a generated dataset and score it.

uv run python -m optiagent_eval.run --model qwen3:8b [--limit 5] [--ids T01,A02]
"""

from __future__ import annotations

import argparse
import asyncio
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from optiagent_agent.llm import LLM, LLMError, OllamaLLM, Trace
from optiagent_agent.pipeline import analyze, extract_from_text
from optiagent_agent.prompts import PROMPT_VERSION
from optiagent_core.pipeline import solve_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem
from optiagent_core.solver import SolveStatus
from optiagent_eval.generate import DATASET, DEFAULT_PATH, Item, load

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
Problem = TransportationProblem | AssignmentProblem


class Diff(BaseModel):
    category: str
    detail: str


class ItemResult(BaseModel):
    id: str
    kind: str
    style: str
    features: list[str]
    predicted_kind: str | None = None
    questions: list[str] = Field(default_factory=list)
    extracted: bool = False
    executed: bool = False
    status: str | None = None
    objective: float | None = None
    expected_objective: float | None = None
    correct: bool = False
    ungrounded: int = 0
    diffs: list[Diff] = Field(default_factory=list)
    llm_calls: int = 0
    latency_ms: float = 0.0
    error: str | None = None


class Summary(BaseModel):
    dataset: str
    model: str
    prompt_version: str
    started_at: datetime
    items: int
    supported: int
    classification_accuracy: float
    unnecessary_question_rate: float
    extraction_rate: float
    execution_rate: float
    objective_accuracy: float
    structure_exact_rate: float
    grounding_flag_rate: float
    mean_llm_calls: float
    mean_latency_s: float
    diff_categories: dict[str, int]


def compare(truth: Problem, got: Problem) -> list[Diff]:
    """Structural differences between the true and the extracted problem."""
    diffs: list[Diff] = []

    def close(a: float | None, b: float | None) -> bool:
        if a is None or b is None:
            return a is b
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)

    if truth.kind != got.kind:
        return [Diff(category="wrong_kind", detail=f"{truth.kind} vs {got.kind}")]
    if truth.sense != got.sense:
        diffs.append(Diff(category="wrong_sense", detail=f"{truth.sense} vs {got.sense}"))

    def compare_values(category: str, a: dict[str, float], b: dict[str, float]) -> None:
        for k in a.keys() - b.keys():
            diffs.append(Diff(category=f"missing_{category}", detail=k))
        for k in b.keys() - a.keys():
            diffs.append(Diff(category=f"extra_{category}", detail=k))
        for k in a.keys() & b.keys():
            if not close(a[k], b[k]):
                diffs.append(
                    Diff(category=f"wrong_{category}_value", detail=f"{k}: {a[k]:g} vs {b[k]:g}")
                )

    if isinstance(truth, TransportationProblem) and isinstance(got, TransportationProblem):
        compare_values(
            "source", {s.id: s.supply for s in truth.sources}, {s.id: s.supply for s in got.sources}
        )
        compare_values(
            "destination",
            {d.id: d.demand for d in truth.destinations},
            {d.id: d.demand for d in got.destinations},
        )
        compare_values(
            "route",
            {f"{r.source}->{r.destination}": r.cost for r in truth.routes},
            {f"{r.source}->{r.destination}": r.cost for r in got.routes},
        )
        t_caps = {
            f"{r.source}->{r.destination}": r.capacity
            for r in truth.routes
            if r.capacity is not None
        }
        g_caps = {
            f"{r.source}->{r.destination}": r.capacity for r in got.routes if r.capacity is not None
        }
        compare_values("route_capacity", t_caps, g_caps)
        if truth.demand_constraint != got.demand_constraint:
            diffs.append(
                Diff(
                    category="wrong_demand_direction",
                    detail=f"{truth.demand_constraint} vs {got.demand_constraint}",
                )
            )
    elif isinstance(truth, AssignmentProblem) and isinstance(got, AssignmentProblem):
        compare_values(
            "agent",
            {a.id: a.capacity for a in truth.agents},
            {a.id: a.capacity for a in got.agents},
        )
        compare_values(
            "task", {t.id: t.required for t in truth.tasks}, {t.id: t.required for t in got.tasks}
        )
        compare_values(
            "pairing",
            {f"{p.agent}->{p.task}": p.value for p in truth.pairings},
            {f"{p.agent}->{p.task}": p.value for p in got.pairings},
        )
    return diffs


async def run_item(llm: LLM, item: Item) -> ItemResult:
    result = ItemResult(
        id=item.id, kind=item.kind, style=item.style, features=item.features,
        expected_objective=item.expected_objective,
    )  # fmt: skip
    trace = Trace()
    try:
        analysis, _ = await analyze(llm, item.text, trace=trace)
        result.predicted_kind = analysis.kind
        result.questions = analysis.questions
        if item.kind == "unsupported" or analysis.kind == "unsupported":
            return result
        extraction = await extract_from_text(llm, item.text, analysis.kind, trace=trace)
        result.extracted = extraction.problem is not None
        result.ungrounded = len(extraction.ungrounded)
        if extraction.problem is None or item.problem is None:
            return result
        result.diffs = compare(item.problem, extraction.problem)
        report = solve_problem(extraction.problem)
        result.status = report.result.status
        result.executed = report.result.status == SolveStatus.OPTIMAL and report.verified
        result.objective = report.result.objective
        result.correct = (
            result.executed
            and item.expected_objective is not None
            and math.isclose(result.objective or 0, item.expected_objective, rel_tol=1e-6)
        )
    except LLMError as exc:
        result.error = str(exc)
    finally:
        result.llm_calls = len(trace.calls)
        result.latency_ms = trace.total_latency_ms
    return result


def summarize(results: list[ItemResult], model: str, started: datetime) -> Summary:
    supported = [r for r in results if r.kind != "unsupported"]
    n = max(len(supported), 1)
    categories: dict[str, int] = {}
    for r in supported:
        for d in r.diffs:
            categories[d.category] = categories.get(d.category, 0) + 1
    return Summary(
        dataset=DATASET,
        model=model,
        prompt_version=PROMPT_VERSION,
        started_at=started,
        items=len(results),
        supported=len(supported),
        classification_accuracy=sum(r.predicted_kind == r.kind for r in results)
        / max(len(results), 1),
        unnecessary_question_rate=sum(bool(r.questions) for r in supported) / n,
        extraction_rate=sum(r.extracted for r in supported) / n,
        execution_rate=sum(r.executed for r in supported) / n,
        objective_accuracy=sum(r.correct for r in supported) / n,
        structure_exact_rate=sum(r.extracted and not r.diffs for r in supported) / n,
        grounding_flag_rate=sum(r.ungrounded > 0 for r in supported) / n,
        mean_llm_calls=sum(r.llm_calls for r in results) / max(len(results), 1),
        mean_latency_s=sum(r.latency_ms for r in results) / max(len(results), 1) / 1000,
        diff_categories=dict(sorted(categories.items(), key=lambda kv: -kv[1])),
    )


class Run(BaseModel):
    summary: Summary
    results: list[ItemResult]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--data", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ids")
    args = parser.parse_args()

    items = load(args.data)
    if args.ids:
        wanted = set(args.ids.split(","))
        items = [i for i in items if i.id in wanted]
    if args.limit:
        items = items[: args.limit]

    llm = OllamaLLM(args.base_url, args.model)
    started = datetime.now(UTC)
    results = []
    for item in items:
        t0 = time.perf_counter()
        r = await run_item(llm, item)
        results.append(r)
        mark = (
            "OK "
            if r.correct or (r.kind == "unsupported" and r.predicted_kind == "unsupported")
            else "ERR"
        )
        print(
            f"{mark} {r.id} {r.kind:<14} pred={r.predicted_kind or '-':<14} calls={r.llm_calls} "
            f"{time.perf_counter() - t0:5.1f}s obj={r.objective} exp={r.expected_objective} "
            f"diffs={[d.category for d in r.diffs]}{' error=' + r.error if r.error else ''}",
            flush=True,
        )

    summary = summarize(results, args.model, started)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S")
    out = RESULTS_DIR / f"{DATASET}__{args.model.replace(':', '-')}__{stamp}.json"
    out.write_text(
        Run(summary=summary, results=results).model_dump_json(indent=2), encoding="utf-8"
    )
    print()
    for key, value in summary.model_dump().items():
        print(f"{key:>28}: {value}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())

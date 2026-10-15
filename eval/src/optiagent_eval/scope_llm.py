"""Out-of-scope detection with the LLM analysis step, alone and combined with the patterns.

uv run python -m optiagent_eval.scope_llm --model qwen3:8b

The analysis step labels each request transportation / assignment / unsupported. A request
counts as flagged by the LLM when it says "unsupported", and by the combination when either
the LLM or the unsupported-semantics patterns flag it. Scored on both scope sets; scope_v1 was
used to tune the patterns (optimistic for them), scope_v2 was not.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from pydantic import BaseModel, SecretStr

from optiagent_agent.llm import LLMError
from optiagent_agent.pipeline import analyze
from optiagent_agent.providers import LLMConfig, make_llm
from optiagent_agent.traceability import unsupported_statements
from optiagent_eval.generate import DEFAULT_PATH, load
from optiagent_eval.handwritten import items as handwritten_items
from optiagent_eval.verification import SCOPE_HELD_OUT, SCOPE_TUNING, Rate, rate

RESULTS = Path(__file__).resolve().parents[2] / "results"


class ScopeItem(BaseModel):
    id: str
    label: str
    llm_kind: str | None
    """None when the LLM call failed (counted as not flagged)."""
    patterns: bool
    latency_s: float


class DetectorRates(BaseModel):
    recall: Rate
    false_positive_rate: Rate


class ScopeLLMResult(BaseModel):
    dataset: str
    model: str
    llm: DetectorRates
    patterns: DetectorRates
    either: DetectorRates
    llm_failures: int
    items: list[ScopeItem]


def _rates(items: list[ScopeItem], flagged: dict[str, bool]) -> DetectorRates:
    bad = [i.id for i in items if i.label == "unsupported"]
    good = [i.id for i in items if i.label == "supported"]
    return DetectorRates(
        recall=rate(sum(flagged[i] for i in bad), len(bad)),
        false_positive_rate=rate(sum(flagged[i] for i in good), len(good)),
    )


def _rows(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def problem_set_rows() -> list[dict[str, str]]:
    """The generated and hand-written problem sets as scope items: mostly supported problems,
    so they measure whether the AI wrongly rejects ordinary requests."""
    items = load(DEFAULT_PATH) + handwritten_items()
    return [
        {
            "id": i.id,
            "label": "unsupported" if i.kind == "unsupported" else "supported",
            "text": i.text,
        }
        for i in items
    ]


async def evaluate(
    name: str, rows: list[dict[str, str]], llm_model: str, llm: object
) -> ScopeLLMResult:
    items = []
    for row in rows:
        t0 = time.perf_counter()
        try:
            analysis, _ = await analyze(llm, row["text"])  # type: ignore[arg-type]
            kind: str | None = analysis.kind
        except LLMError:
            kind = None
        patterns = any(r.status == "unsupported" for r in unsupported_statements(row["text"]))
        item = ScopeItem(
            id=row["id"],
            label=row["label"],
            llm_kind=kind,
            patterns=patterns,
            latency_s=round(time.perf_counter() - t0, 1),
        )
        items.append(item)
        print(f"{name} {item.id} {item.label:<11} llm={kind} patterns={patterns}", flush=True)
    by_llm = {i.id: i.llm_kind == "unsupported" for i in items}
    by_patterns = {i.id: i.patterns for i in items}
    return ScopeLLMResult(
        dataset=name,
        model=llm_model,
        llm=_rates(items, by_llm),
        patterns=_rates(items, by_patterns),
        either=_rates(items, {k: by_llm[k] or by_patterns[k] for k in by_llm}),
        llm_failures=sum(i.llm_kind is None for i in items),
        items=items,
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--provider", choices=["ollama", "openai"], default="ollama")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--api-key-env", default="OPTIAGENT_LLM_API_KEY")
    args = parser.parse_args()
    key = os.environ.get(args.api_key_env)
    llm = make_llm(
        LLMConfig(
            provider=args.provider,
            base_url=args.base_url,
            model=args.model,
            api_key=SecretStr(key) if key else None,
        )
    )
    sets = [
        (SCOPE_TUNING.stem, _rows(SCOPE_TUNING)),
        (SCOPE_HELD_OUT.stem, _rows(SCOPE_HELD_OUT)),
        ("problem sets (nl_v1 + handwritten_v1)", problem_set_rows()),
    ]
    results = [await evaluate(name, rows, args.model, llm) for name, rows in sets]
    out = RESULTS / f"scope_llm__{args.model.replace(':', '-').replace('/', '-')}.json"
    out.write_text(
        json.dumps([r.model_dump(mode="json") for r in results], indent=2), encoding="utf-8"
    )
    for r in results:
        print(f"\n{r.dataset} ({r.model}), {r.llm_failures} LLM failures")
        for name in ("llm", "patterns", "either"):
            d: DetectorRates = getattr(r, name)
            print(
                f"  {name:<9} recall {d.recall.k}/{d.recall.n}  "
                f"false positives {d.false_positive_rate.k}/{d.false_positive_rate.n}"
            )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())

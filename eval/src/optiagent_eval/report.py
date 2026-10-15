"""Combine evaluation runs into one summary (JSON for the app, Markdown for the repo).

The audit is re-scored on the stored extractions with the current code, so audit numbers
always reflect the audit as it is now, without re-running the LLM.

    uv run python -m optiagent_eval.report
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from optiagent_agent.audit import audit
from optiagent_agent.traceability import trace
from optiagent_eval.generate import DEFAULT_PATH, load
from optiagent_eval.handwritten import items as handwritten_items
from optiagent_eval.mutations import AuditEval, evaluate
from optiagent_eval.run import RESULTS_DIR, Run
from optiagent_eval.scope_llm import ScopeLLMResult
from optiagent_eval.verification import Rate, VerificationBenchmark
from optiagent_eval.verification import run as run_verification

SUMMARY = RESULTS_DIR / "summary_v1.json"
OPEN = {"unresolved", "unsupported"}
REPORT = RESULTS_DIR.parent / "REPORT.md"


class ModeRow(BaseModel):
    mode: str
    model: str
    file: str
    supported: int
    classification_accuracy: float
    execution_rate: float
    objective_accuracy: float
    structure_exact_rate: float
    wrong_models: int
    audit_caught: int
    audit_false_alarms: int
    silent_error_rate: float
    mean_llm_calls: float
    mean_latency_s: float
    unnecessary_question_rate: float
    diff_categories: dict[str, int]


class AuditRow(BaseModel):
    dataset: str
    problems: int
    false_alarms: int
    injected: int
    detected: int
    categories: dict[str, list[int]]


class Summary(BaseModel):
    generated_at: datetime
    modes: list[ModeRow]
    audit: list[AuditRow]
    verification: VerificationBenchmark | None = None
    scope_llm: list[ScopeLLMResult] = Field(default_factory=list)
    """LLM out-of-scope detection, from stored runs of optiagent_eval.scope_llm."""
    notes: list[str]


def _latest_runs() -> list[tuple[str, Path]]:
    """The most recent run for each (mode, model), ordered by mode then model."""
    latest: dict[tuple[str, str], Path] = {}
    for path in sorted(RESULTS_DIR.glob("nl_v1__*__*__*.json")):
        _, mode, model, _stamp = path.stem.split("__")
        latest[(mode, model)] = path  # later timestamps overwrite earlier ones
    order = {"direct": 0, "no-verify": 1, "full": 2}
    return [
        (mode, path)
        for (mode, _), path in sorted(
            latest.items(), key=lambda kv: (kv[0][1], order.get(kv[0][0], 9))
        )
    ]


def _rescore(run: Run) -> Run:
    """Recompute the warnings the app would show on stored extractions, with the current code:
    audit findings plus open (unresolved or unsupported) traceability items."""
    texts = {i.id: i.text for i in load(DEFAULT_PATH)}
    for r in run.results:
        if r.extracted_problem is not None:
            text = texts[r.id]
            traced = trace(r.extracted_problem, text)
            r.audit_flags = [
                f.message for f in audit(r.extracted_problem, text).findings if f.severity != "info"
            ]
            r.audit_flags += [
                f"{x.parameter}: {x.evidence}" for x in traced.provenance if x.status in OPEN
            ]
            r.audit_flags += [x.interpretation for x in traced.requirements if x.status in OPEN]
    return run


def _mode_row(mode: str, path: Path) -> ModeRow:
    run = Run.model_validate_json(path.read_text(encoding="utf-8"))
    if mode == "full":
        run = _rescore(run)
    supported = [r for r in run.results if r.kind != "unsupported"]
    n = max(len(supported), 1)
    wrong = [r for r in supported if r.wrong]
    caught = [r for r in wrong if r.audit_flags]
    false_alarms = [r for r in supported if r.extracted and not r.wrong and r.audit_flags]
    silent = sum(not r.correct for r in supported) if mode == "direct" else len(wrong) - len(caught)
    diffs = Counter(d.category for r in supported for d in r.diffs)
    s = run.summary
    return ModeRow(
        mode=mode,
        model=s.model,
        file=path.name,
        supported=len(supported),
        classification_accuracy=s.classification_accuracy,
        execution_rate=s.execution_rate,
        objective_accuracy=s.objective_accuracy,
        structure_exact_rate=s.structure_exact_rate,
        wrong_models=len(wrong),
        audit_caught=len(caught),
        audit_false_alarms=len(false_alarms),
        silent_error_rate=silent / n,
        mean_llm_calls=s.mean_llm_calls,
        mean_latency_s=s.mean_latency_s,
        unnecessary_question_rate=s.unnecessary_question_rate,
        diff_categories=dict(diffs.most_common()),
    )


def _audit_row(name: str, result: AuditEval) -> AuditRow:
    return AuditRow(
        dataset=name,
        problems=result.problems,
        false_alarms=result.false_alarms,
        injected=result.injected,
        detected=result.detected,
        categories={c.category: [c.detected, c.injected] for c in result.categories},
    )


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _rate(r: Rate) -> str:
    return f"{r.value:.0%} ({r.k}/{r.n}; 95% CI {r.low:.0%}–{r.high:.0%})"


def _scope_llm_markdown(results: list[ScopeLLMResult]) -> list[str]:
    lines = [
        "### Out-of-scope requests: AI analysis vs patterns",
        "",
        "The analysis step labels each request; 'either' flags a request when the AI or the "
        "patterns do. scope_v1 tuned the patterns, so their v1 numbers are optimistic. The "
        "problem sets are the 32 supported problems above (plus 3 unsupported): false positives "
        "there mean an ordinary request was wrongly rejected. One run per model; the 2B model's "
        "answers vary between runs (held-out recall 3/12 and 4/12 on two runs).",
        "",
        "| Set | Model | Detector | Recall | False-positive rate |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        for name in ("llm", "patterns", "either"):
            d = getattr(r, name)
            label = {"llm": "AI analysis", "patterns": "patterns", "either": "either"}[name]
            lines.append(
                f"| {r.dataset} | {r.model} | {label} | {_rate(d.recall)} | "
                f"{_rate(d.false_positive_rate)} |"
            )
    lines.append("")
    return lines


def _load_scope_llm() -> list[ScopeLLMResult]:
    out: list[ScopeLLMResult] = []
    for path in sorted(RESULTS_DIR.glob("scope_llm__*.json")):
        out += [ScopeLLMResult.model_validate(r) for r in json.loads(path.read_text("utf-8"))]
    return out


def _verification_markdown(v: VerificationBenchmark) -> list[str]:
    lines = [
        "",
        "## Deterministic verification benchmark",
        "",
        "No LLM involved; `python -m optiagent_eval.verification`. Recall = injected errors "
        "flagged; FPR = correct models flagged; precision = flagged models that were really "
        "wrong. The two baselines bound the metrics: flagging everything gets full recall and "
        "is useless. Most samples are mutants, so even 'flag everything' has high precision; "
        "the false-positive rate is the number to read for false alarms.",
        "",
        "### Formulation errors (mutated correct models)",
        "",
        "| Dataset | Detector | Recall | False-positive rate | Precision |",
        "|---|---|---|---|---|",
    ]
    for f in v.formulation:
        for d in f.scores:
            lines.append(
                f"| {f.dataset} | {d.detector} | {_rate(d.recall)} | "
                f"{_rate(d.false_positive_rate)} | {_rate(d.precision)} |"
            )
    lines += ["", "Recall by error category (audit + traceability):", ""]
    for f in v.formulation:
        combined = next(d for d in f.scores if d.detector == "audit + traceability")
        cats = ", ".join(f"`{c}` {r.k}/{r.n}" for c, r in combined.by_category.items())
        lines.append(f"- {f.dataset}: {cats}")
        if f.missed_by_all:
            lines.append(f"  - missed by every detector: {', '.join(f.missed_by_all)}")
    b = v.builder_faults
    lines += [
        "",
        "### Model-builder faults",
        "",
        f"The built model is corrupted the way a buggy builder would; {b.harmful} of {b.faults} "
        "faults change the plan into one that breaks the data or is not optimal for it.",
        "",
        "| Check | Harmful faults caught |",
        "|---|---|",
        f"| Layer 1 (plan vs the corrupted model) | {_rate(b.model_checks)} |",
        f"| Problem-level (plan vs the data, incl. duality certificate) | {_rate(b.problem_checks)} |",
        "",
        f"False alarms on correct plans: {_rate(b.false_alarms_on_correct)}.",
        "",
        "### Malformed data",
        "",
        f"One corrupted cell per sample dataset (text, NaN, infinity, negative, blank): "
        f"{_rate(v.malformed_data.detected)} rejected with an error naming the cell; duplicate "
        f"ids {_rate(v.malformed_data.duplicate_ids)}; clean datasets flagged "
        f"{_rate(v.malformed_data.clean_false_alarms)}.",
        "",
        "### Out-of-scope requests (unsupported-semantics detector)",
        "",
        "| Set | Recall (unsupported flagged) | False-positive rate (supported flagged) |",
        "|---|---|---|",
    ]
    for sc in (v.scope_tuning, v.scope_held_out):
        role = "tuning set" if sc is v.scope_tuning else "held out"
        lines.append(
            f"| {sc.dataset} ({role}) | {_rate(sc.recall)} | {_rate(sc.false_positive_rate)} |"
        )
    lines.append("")
    return lines


def markdown(summary: Summary) -> str:
    lines = [
        "# OptiAgent evaluation report",
        "",
        f"_Generated {summary.generated_at:%Y-%m-%d %H:%M} UTC by `python -m optiagent_eval.report`._",
        "",
        "## End to end: natural language to verified optimum",
        "",
        "24 generated transportation/assignment word problems plus 3 out-of-scope problems "
        "(dataset `nl_v1`). Ground truth is known by construction.",
        "",
        "| Mode | Model | Correct optimum | Exact model | Executes | Wrong models | Caught before approval | False alarms | **Silent errors** | LLM calls | Latency / problem |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in summary.modes:
        caught = f"{m.audit_caught}/{m.wrong_models}" if m.mode == "full" else "—"
        alarms = str(m.audit_false_alarms) if m.mode == "full" else "—"
        exact = _pct(m.structure_exact_rate) if m.mode != "direct" else "—"
        executes = _pct(m.execution_rate) if m.mode != "direct" else "—"
        lines.append(
            f"| {m.mode} | {m.model} | {_pct(m.objective_accuracy)} | {exact} | {executes} | "
            f"{m.wrong_models if m.mode != 'direct' else '—'} | {caught} | {alarms} | "
            f"**{_pct(m.silent_error_rate)}** | {m.mean_llm_calls:.1f} | {m.mean_latency_s:.0f} s |"
        )
    lines += [
        "",
        "- **direct**: the LLM states the optimum itself; no model, no solver.",
        "- **no-verify**: one extraction attempt, no grounding feedback, no audit.",
        "- **full**: OptiAgent: grounding retries, deterministic model, solver, audit.",
        "- **Silent errors**: problems that end with a wrong answer and no warning shown to the user.",
        "",
    ]
    for m in summary.modes:
        if m.mode != "direct" and m.diff_categories:
            lines += [f"### Model errors: {m.model}, {m.mode} (structural differences)", ""]
            lines += [f"- `{k}`: {v}" for k, v in m.diff_categories.items()]
            lines.append("")
    lines += [
        "## Formulation audit: injected modelling errors",
        "",
        "Each correct model is mutated one error at a time; the audit must flag the mutant "
        "and must not flag the correct model.",
        "",
        "| Dataset | Problems | False alarms | Errors detected |",
        "|---|---|---|---|",
    ]
    for a in summary.audit:
        lines.append(
            f"| {a.dataset} | {a.problems} | {a.false_alarms}/{a.problems} | "
            f"{a.detected}/{a.injected} ({_pct(a.detected / max(a.injected, 1))}) |"
        )
    if summary.verification is not None:
        lines += _verification_markdown(summary.verification)
    if summary.scope_llm:
        lines += _scope_llm_markdown(summary.scope_llm)
    lines += ["", "## Notes and limitations", ""]
    lines += [f"- {n}" for n in summary.notes]
    return "\n".join(lines) + "\n"


NOTES = [
    "A 'wrong model' differs structurally from the true model or gives the wrong optimum. Some "
    "wrong models still reach the right optimum (for example an invented route limit that never "
    "binds); they are counted because the model no longer matches the problem.",
    "qwen3-vl:2b, full mode: the one wrong model the audit did not flag (T10) only shortened ids "
    "('Depot X' to 'X'); it is otherwise equivalent and its optimum is correct, so all 11 real "
    "modelling errors were flagged.",
    "qwen3:8b made no modelling errors on the generated set, so audit detection on real errors "
    "is measured with the smaller qwen3-vl:2b model.",
    "The generated set is template-based; the audit's text patterns reach 100% detection there "
    "but are partly tuned to those phrasings.",
    "The hand-written set exposed overfitting (8/8 false alarms before the fix). It was then used "
    "to fix the parser, so it is no longer held out. An independent set written by someone else "
    "is needed for an unbiased estimate.",
    "Runs used a laptop GPU (RTX 4050, 6 GB) shared with another local app, so latency includes "
    "model reloads and is not a speed benchmark.",
    "Small samples: 24 generated and 8 hand-written problems. Treat rates as indicative.",
    "'Caught' in full mode counts what the app now shows before approval: audit findings plus "
    "unresolved or unsupported traceability items, re-scored on the stored extractions.",
    "Both scope sets were written by the same author as the unsupported-semantics patterns. "
    "scope_v2 was written before tuning and never used for tuning, but it is not independent; "
    "a set written by someone else is still needed.",
    "Builder faults are synthetic corruptions of correct models. They show that the problem-level "
    "checks do not depend on the model builder; they do not estimate how often real builder "
    "bugs occur.",
    "Traceability alone misses errors whose wrong value also appears elsewhere in the text "
    "(it then only shows as 'represented'): string presence is not semantic verification.",
]


def build() -> Summary:
    modes = [_mode_row(m, p) for m, p in _latest_runs()]
    audits = [
        _audit_row("generated (nl_v1)", evaluate()),
        _audit_row("hand-written (handwritten_v1)", evaluate(items=handwritten_items())),
    ]
    return Summary(
        generated_at=datetime.now(UTC),
        modes=modes,
        audit=audits,
        verification=run_verification(),
        scope_llm=_load_scope_llm(),
        notes=NOTES,
    )


if __name__ == "__main__":
    summary = build()
    SUMMARY.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    REPORT.write_text(markdown(summary), encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))
    print(json.dumps({"summary": str(SUMMARY), "report": str(REPORT)}))

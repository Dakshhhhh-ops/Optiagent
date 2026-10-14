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

from pydantic import BaseModel

from optiagent_agent.audit import audit
from optiagent_eval.generate import DEFAULT_PATH, load
from optiagent_eval.handwritten import items as handwritten_items
from optiagent_eval.mutations import AuditEval, evaluate
from optiagent_eval.run import RESULTS_DIR, Run

SUMMARY = RESULTS_DIR / "summary_v1.json"
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
    """Recompute audit flags on stored extractions with the current audit code."""
    texts = {i.id: i.text for i in load(DEFAULT_PATH)}
    for r in run.results:
        if r.extracted_problem is not None:
            r.audit_flags = [
                f.message
                for f in audit(r.extracted_problem, texts[r.id]).findings
                if f.severity != "info"
            ]
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
        "| Mode | Model | Correct optimum | Exact model | Executes | Wrong models | Caught by audit | Audit false alarms | **Silent errors** | LLM calls | Latency / problem |",
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
]


def build() -> Summary:
    modes = [_mode_row(m, p) for m, p in _latest_runs()]
    audits = [
        _audit_row("generated (nl_v1)", evaluate()),
        _audit_row("hand-written (handwritten_v1)", evaluate(items=handwritten_items())),
    ]
    return Summary(generated_at=datetime.now(UTC), modes=modes, audit=audits, notes=NOTES)


if __name__ == "__main__":
    summary = build()
    SUMMARY.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    REPORT.write_text(markdown(summary), encoding="utf-8")
    print(REPORT.read_text(encoding="utf-8"))
    print(json.dumps({"summary": str(SUMMARY), "report": str(REPORT)}))

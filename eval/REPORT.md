# OptiAgent evaluation report

_Generated 2026-10-14 11:39 UTC by `python -m optiagent_eval.report`._

## End to end: natural language to verified optimum

24 generated transportation/assignment word problems plus 3 out-of-scope problems (dataset `nl_v1`). Ground truth is known by construction.

| Mode | Model | Correct optimum | Exact model | Executes | Wrong models | Caught by audit | Audit false alarms | **Silent errors** | LLM calls | Latency / problem |
|---|---|---|---|---|---|---|---|---|---|---|

- **direct**: the LLM states the optimum itself; no model, no solver.
- **no-verify**: one extraction attempt, no grounding feedback, no audit.
- **full**: OptiAgent: grounding retries, deterministic model, solver, audit.
- **Silent errors**: problems that end with a wrong answer and no warning shown to the user.

## Formulation audit: injected modelling errors

Each correct model is mutated one error at a time; the audit must flag the mutant and must not flag the correct model.

| Dataset | Problems | False alarms | Errors detected |
|---|---|---|---|
| generated (nl_v1) | 24 | 0/24 | 204/204 (100%) |
| hand-written (handwritten_v1) | 8 | 0/8 | 62/68 (91%) |

## Notes and limitations

- The generated set is template-based; the audit's text patterns reach 100% detection there but are partly tuned to those phrasings.
- The hand-written set exposed overfitting (8/8 false alarms before the fix). It was then used to fix the parser, so it is no longer held out. An independent set written by someone else is needed for an unbiased estimate.
- Runs used a laptop GPU (RTX 4050, 6 GB) shared with another local app, so latency includes model reloads and is not a speed benchmark.
- Small samples: 24 generated and 8 hand-written problems. Treat rates as indicative.

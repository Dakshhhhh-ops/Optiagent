# OptiAgent evaluation report

_Generated 2026-10-14 12:34 UTC by `python -m optiagent_eval.report`._

## End to end: natural language to verified optimum

24 generated transportation/assignment word problems plus 3 out-of-scope problems (dataset `nl_v1`). Ground truth is known by construction.

| Mode | Model | Correct optimum | Exact model | Executes | Wrong models | Caught by audit | Audit false alarms | **Silent errors** | LLM calls | Latency / problem |
|---|---|---|---|---|---|---|---|---|---|---|
| direct | qwen3:8b | 4% | — | — | — | — | — | **96%** | 0.9 | 1 s |
| no-verify | qwen3:8b | 92% | 92% | 92% | 0 | — | — | **0%** | 1.9 | 57 s |
| full | qwen3:8b | 100% | 100% | 100% | 0 | 0/0 | 0 | **0%** | 2.0 | 56 s |
| no-verify | qwen3-vl:2b-instruct | 79% | 46% | 96% | 12 | — | — | **50%** | 1.9 | 9 s |
| full | qwen3-vl:2b-instruct | 79% | 46% | 96% | 12 | 11/12 | 0 | **4%** | 2.1 | 11 s |

- **direct**: the LLM states the optimum itself; no model, no solver.
- **no-verify**: one extraction attempt, no grounding feedback, no audit.
- **full**: OptiAgent: grounding retries, deterministic model, solver, audit.
- **Silent errors**: problems that end with a wrong answer and no warning shown to the user.

### Model errors: qwen3-vl:2b-instruct, no-verify (structural differences)

- `extra_route_capacity`: 15
- `missing_pairing`: 11
- `extra_route`: 10
- `missing_route`: 9
- `extra_pairing`: 4
- `missing_source`: 3
- `extra_source`: 3
- `missing_route_capacity`: 1
- `wrong_demand_direction`: 1

### Model errors: qwen3-vl:2b-instruct, full (structural differences)

- `extra_route_capacity`: 15
- `extra_route`: 10
- `missing_route`: 9
- `missing_pairing`: 6
- `extra_pairing`: 5
- `missing_source`: 3
- `extra_source`: 3
- `missing_route_capacity`: 1
- `wrong_demand_direction`: 1

## Formulation audit: injected modelling errors

Each correct model is mutated one error at a time; the audit must flag the mutant and must not flag the correct model.

| Dataset | Problems | False alarms | Errors detected |
|---|---|---|---|
| generated (nl_v1) | 24 | 0/24 | 204/204 (100%) |
| hand-written (handwritten_v1) | 8 | 0/8 | 62/68 (91%) |

## Notes and limitations

- A 'wrong model' differs structurally from the true model or gives the wrong optimum. Some wrong models still reach the right optimum (for example an invented route limit that never binds); they are counted because the model no longer matches the problem.
- qwen3-vl:2b, full mode: the one wrong model the audit did not flag (T10) only shortened ids ('Depot X' to 'X'); it is otherwise equivalent and its optimum is correct, so all 11 real modelling errors were flagged.
- qwen3:8b made no modelling errors on the generated set, so audit detection on real errors is measured with the smaller qwen3-vl:2b model.
- The generated set is template-based; the audit's text patterns reach 100% detection there but are partly tuned to those phrasings.
- The hand-written set exposed overfitting (8/8 false alarms before the fix). It was then used to fix the parser, so it is no longer held out. An independent set written by someone else is needed for an unbiased estimate.
- Runs used a laptop GPU (RTX 4050, 6 GB) shared with another local app, so latency includes model reloads and is not a speed benchmark.
- Small samples: 24 generated and 8 hand-written problems. Treat rates as indicative.

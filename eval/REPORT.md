# OptiAgent evaluation report

_Generated 2026-10-15 06:15 UTC by `python -m optiagent_eval.report`._

## End to end: natural language to verified optimum

24 generated transportation/assignment word problems plus 3 out-of-scope problems (dataset `nl_v1`). Ground truth is known by construction.

| Mode | Model | Correct optimum | Exact model | Executes | Wrong models | Caught before approval | False alarms | **Silent errors** | LLM calls | Latency / problem |
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

## Deterministic verification benchmark

No LLM involved; `python -m optiagent_eval.verification`. Recall = injected errors flagged; FPR = correct models flagged; precision = flagged models that were really wrong. The two baselines bound the metrics: flagging everything gets full recall and is useless. Most samples are mutants, so even 'flag everything' has high precision; the false-positive rate is the number to read for false alarms.

### Formulation errors (mutated correct models)

| Dataset | Detector | Recall | False-positive rate | Precision |
|---|---|---|---|---|
| generated (nl_v1) | no verification (baseline) | 0% (0/204; 95% CI 0%–2%) | 0% (0/24; 95% CI 0%–14%) | 0% (0/0; 95% CI 0%–100%) |
| generated (nl_v1) | flag everything (baseline) | 100% (204/204; 95% CI 98%–100%) | 100% (24/24; 95% CI 86%–100%) | 89% (204/228; 95% CI 85%–93%) |
| generated (nl_v1) | audit | 100% (204/204; 95% CI 98%–100%) | 0% (0/24; 95% CI 0%–14%) | 100% (204/204; 95% CI 98%–100%) |
| generated (nl_v1) | traceability | 77% (158/204; 95% CI 71%–83%) | 0% (0/24; 95% CI 0%–14%) | 100% (158/158; 95% CI 98%–100%) |
| generated (nl_v1) | audit + traceability | 100% (204/204; 95% CI 98%–100%) | 0% (0/24; 95% CI 0%–14%) | 100% (204/204; 95% CI 98%–100%) |
| hand-written (handwritten_v1) | no verification (baseline) | 0% (0/68; 95% CI 0%–5%) | 0% (0/8; 95% CI 0%–32%) | 0% (0/0; 95% CI 0%–100%) |
| hand-written (handwritten_v1) | flag everything (baseline) | 100% (68/68; 95% CI 95%–100%) | 100% (8/8; 95% CI 68%–100%) | 89% (68/76; 95% CI 81%–95%) |
| hand-written (handwritten_v1) | audit | 91% (62/68; 95% CI 82%–96%) | 0% (0/8; 95% CI 0%–32%) | 100% (62/62; 95% CI 94%–100%) |
| hand-written (handwritten_v1) | traceability | 78% (53/68; 95% CI 67%–86%) | 0% (0/8; 95% CI 0%–32%) | 100% (53/53; 95% CI 93%–100%) |
| hand-written (handwritten_v1) | audit + traceability | 94% (64/68; 95% CI 86%–98%) | 0% (0/8; 95% CI 0%–32%) | 100% (64/64; 95% CI 94%–100%) |

Recall by error category (audit + traceability):

- generated (nl_v1): `extra_capacity` 12/12, `extra_pair` 6/6, `extra_route` 4/4, `flipped_demand_direction` 12/12, `flipped_sense` 24/24, `missing_capacity` 4/4, `missing_pair` 12/12, `missing_route` 12/12, `swapped_values` 22/22, `unit_scale` 24/24, `wrong_capacity` 12/12, `wrong_cost` 12/12, `wrong_demand` 12/12, `wrong_required` 12/12, `wrong_supply` 12/12, `wrong_value` 12/12
- hand-written (handwritten_v1): `extra_capacity` 4/4, `extra_pair` 1/1, `extra_route` 1/1, `flipped_demand_direction` 4/4, `flipped_sense` 8/8, `missing_capacity` 2/2, `missing_pair` 4/4, `missing_route` 4/4, `swapped_values` 7/8, `unit_scale` 8/8, `wrong_capacity` 2/4, `wrong_cost` 4/4, `wrong_demand` 4/4, `wrong_required` 3/4, `wrong_supply` 4/4, `wrong_value` 4/4
  - missed by every detector: H03:swapped_values, H03:wrong_required, H03:wrong_capacity, H04:wrong_capacity

### Model-builder faults

The built model is corrupted the way a buggy builder would; 107 of 182 faults change the plan into one that breaks the data or is not optimal for it.

| Check | Harmful faults caught |
|---|---|
| Layer 1 (plan vs the corrupted model) | 0% (0/107; 95% CI 0%–3%) |
| Problem-level (plan vs the data, incl. duality certificate) | 100% (107/107; 95% CI 97%–100%) |

False alarms on correct plans: 0% (0/32; 95% CI 0%–11%).

### Malformed data

One corrupted cell per sample dataset (text, NaN, infinity, negative, blank): 100% (15/15; 95% CI 80%–100%) rejected with an error naming the cell; duplicate ids 100% (3/3; 95% CI 44%–100%); clean datasets flagged 0% (0/3; 95% CI 0%–56%).

### Out-of-scope requests (unsupported-semantics detector)

| Set | Recall (unsupported flagged) | False-positive rate (supported flagged) |
|---|---|---|
| scope_v1 (tuning set) | 100% (15/15; 95% CI 80%–100%) | 0% (0/15; 95% CI 0%–20%) |
| scope_v2 (held out) | 75% (9/12; 95% CI 47%–91%) | 0% (0/12; 95% CI 0%–24%) |


## Notes and limitations

- A 'wrong model' differs structurally from the true model or gives the wrong optimum. Some wrong models still reach the right optimum (for example an invented route limit that never binds); they are counted because the model no longer matches the problem.
- qwen3-vl:2b, full mode: the one wrong model the audit did not flag (T10) only shortened ids ('Depot X' to 'X'); it is otherwise equivalent and its optimum is correct, so all 11 real modelling errors were flagged.
- qwen3:8b made no modelling errors on the generated set, so audit detection on real errors is measured with the smaller qwen3-vl:2b model.
- The generated set is template-based; the audit's text patterns reach 100% detection there but are partly tuned to those phrasings.
- The hand-written set exposed overfitting (8/8 false alarms before the fix). It was then used to fix the parser, so it is no longer held out. An independent set written by someone else is needed for an unbiased estimate.
- Runs used a laptop GPU (RTX 4050, 6 GB) shared with another local app, so latency includes model reloads and is not a speed benchmark.
- Small samples: 24 generated and 8 hand-written problems. Treat rates as indicative.
- 'Caught' in full mode counts what the app now shows before approval: audit findings plus unresolved or unsupported traceability items, re-scored on the stored extractions.
- Both scope sets were written by the same author as the unsupported-semantics patterns. scope_v2 was written before tuning and never used for tuning, but it is not independent; a set written by someone else is still needed.
- Builder faults are synthetic corruptions of correct models. They show that the problem-level checks do not depend on the model builder; they do not estimate how often real builder bugs occur.
- Traceability alone misses errors whose wrong value also appears elsewhere in the text (it then only shows as 'represented'): string presence is not semantic verification.

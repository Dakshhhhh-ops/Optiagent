# Correctness audit (2026-10-15)

A skeptical review of OptiAgent's claim: *the LLM proposes, deterministic code builds and solves,
independent checks verify, and the user approves the exact formulation.* Findings are ranked by
how much damage they could do to a user who trusts the result. Every "confirmed" item was
reproduced before it was fixed and has a regression test.

Baseline before the audit: ruff, ruff format, mypy (strict) and 199 tests passed; CI green.
After: 339 tests pass (Python), web lint and typecheck pass, CI green.

## Confirmed defects (fixed)

| # | Severity | Defect | How it was found | Fix | Test |
|---|---|---|---|---|---|
| 1 | High | "Verified" only meant *the plan satisfies the model it was given*. A model-builder bug (dropped row, flipped sign, wrong coefficient) was checked against the same wrong model and still showed **Verified optimal**. | Builder-fault benchmark: Layer 1 caught 0/107 harmful faults. | `plancheck.py` re-checks the plan against the original problem data (supplies, demands, capacities, staffing, objective) and adds a **duality certificate** that proves optimality from the data. Plans failing it are not shown as business plans. | `core/tests/test_verification.py` |
| 2 | High | A project could be "Verified" while its model contradicted the description (wrong objective direction, invented numbers). Plan verification and formulation correctness were one badge. | Code review of the save path and UI. | Requirement traceability stored with each project; separate *Plan verified* and *Formulation* badges. | `api/tests/test_traceability_api.py` |
| 3 | High | Requests the model cannot express (fixed costs, budgets, multi-period, single sourcing, lot sizes, transshipment...) were silently simplified if the LLM extracted something solvable. | Review against the spec. | Unsupported-semantics detector; such requests show as **unsupported** and the approval button says so. | `agent/tests/test_traceability.py` |
| 4 | High | One bad cell in an optional table (e.g. task requirements) made the whole table invisible, and every task **silently defaulted to 1 agent**. | Malformed-data benchmark (13/15 before). | A mostly-numeric column stays numeric; the loader reports the exact cell. | `test_bad_cell_in_optional_table_is_reported_not_defaulted` |
| 5 | Medium | NaN and infinity were accepted as costs and quantities (JSON, Python, and cells like `1e999`), reaching the solver as garbage. | Probe script. | `allow_inf_nan=False` on every schema model; file cells must be finite. | `test_non_finite_*`, `test_file_cells_never_parse_to_non_finite` |
| 6 | Medium | Cost tables mixing currencies (`₹40`, `$3`) were merged into one set of numbers. | Code review of `parse_number`. | Error naming the currencies and rows. | `test_mixed_currencies_are_an_error_not_silently_merged` |
| 7 | Medium | Sensitivity said "one less unit **would make the plan infeasible**" for a zero requirement, where a decrease is simply impossible. | Probe script. | One-unit effects carry a status: changed / infeasible / not applicable / solver failed. | `test_zero_requirement_cannot_be_decreased` |
| 8 | Medium | Ties were hidden: with two equally good plans, one was presented as *the* optimum. | Probe script. | Alternative optima are **proven** by re-solving (maximize the unused variable at the optimal objective) and reported. | `test_tied_routes_are_reported_as_alternative_optima` |
| 9 | Low | Route-limit effects used the reduced cost ("by about"), a local estimate presented as a result. | Code review. | Exact re-solve with the limit raised by one. | `test_route_limit_effect_is_an_exact_resolve` |
| 10 | Low | Every non-optimal solver status became "No feasible solution"; a time limit or solver error read as infeasible. No time limit existed. | Code review. | Distinct outcomes (infeasible, unbounded, time limit, invalid model, solver error, verification failed) in the API and UI; 60 s solver limit. | `test_outcomes_are_distinct` |
| 11 | Low | The infeasibility diagnosis did not state its relaxation or weights. | Code review. | The diagnosis carries its method: equal weights on demand/staffing shortfall, all other limits hard, split not unique. | `test_outcomes_are_distinct` |
| 12 | Low | File-based projects claimed their numbers came from the upload, without checking. | Code review. | On save, the server re-loads the stored upload with the mapping and compares. Edited values become unresolved. | `test_file_provenance_is_rechecked_on_the_server` |

## What the checks establish, and what they do not

| Claim shown to the user | Established by | Strength |
|---|---|---|
| Plan verified | Solver status, re-check against the model, re-check against the data, duality certificate | Proof (to 1e-6 relative tolerance) that the plan is optimal **for the approved data** |
| Value *verified* in traceability | A text pattern links a statement to this element and the numbers match exactly | Strong for the phrasings the parser knows; silent on others |
| Value *represented* | The number appears in the text, or only an AI review says "covered" | Weak: string presence is not meaning |
| *Unsupported* | Fixed patterns over the description | Held-out recall 75% (9/12), 0/12 false alarms; misses unusual phrasings |
| AI requirement review | LLM opinion | Can only flag; never verifies anything |

## Hypotheses and remaining risks (not fixed)

1. **Text facts are pattern-based.** Statements phrased in ways the parser does not know are not
   linked; their numbers fall back to "represented". A wrong value that also appears elsewhere in
   the text is then not flagged (4 of 68 hand-written mutants are missed by every detector).
2. **The unsupported-semantics detector is a keyword net**, not understanding. It missed
   "served entirely by one depot", "pass through a cross-dock" and a discount curve in the held-out
   set. The LLM analysis step also labels unsupported problems, but its accuracy is only measured
   on 3 examples.
3. **Units are not modelled.** Currency mixing in files is caught; mixed units in text ("tons" vs
   "kg") are not.
4. **Evaluation sets are small and written by the developer.** Rates carry wide confidence
   intervals and may not transfer to real users' writing. An independent problem set is the
   single most valuable next step.
5. **Rate limits are in memory**, correct for one API instance only (documented in DEPLOY.md).
6. **Clerk sign-in has not been exercised with real keys**; the token verification is unit-tested
   with locally signed tokens.

## How to reproduce

```bash
uv run pytest -q                                  # all deterministic tests
uv run python -m optiagent_eval.verification      # benchmark: formulation errors, builder faults,
                                                  # malformed data, out-of-scope requests
uv run python -m optiagent_eval.report            # regenerates eval/REPORT.md
```

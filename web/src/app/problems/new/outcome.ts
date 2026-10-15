import type { SolveReport } from "@/lib/api";

/** How each solve outcome is described. Infeasible, time limit and solver errors are different
 * claims and must never be shown with the same words. */
export const OUTCOME: Record<SolveReport["outcome"], { badge: string; title: string; text: string }> = {
  verified_optimal: { badge: "Plan verified", title: "Optimal plan", text: "" },
  verification_failed: {
    badge: "Verification failed",
    title: "The plan failed verification",
    text: "The solver returned a plan, but the independent checks rejected it, so it is not shown as a business plan.",
  },
  infeasible: {
    badge: "Infeasible",
    title: "No plan satisfies every requirement",
    text: "The solver proved that no plan meets all the limits.",
  },
  unbounded: {
    badge: "Unbounded",
    title: "The objective can improve without limit",
    text: "This usually means a limit is missing from the model.",
  },
  time_limit: {
    badge: "Not proven",
    title: "Stopped at the time limit",
    text: "The solver neither found an optimal plan nor proved there is none. Nothing is claimed about feasibility.",
  },
  invalid_model: {
    badge: "Invalid model",
    title: "The solver rejected the model",
    text: "The model contains values the solver cannot use.",
  },
  solver_error: {
    badge: "Solver error",
    title: "The solver failed",
    text: "No result was proven. Try again; if it repeats, the problem may be too large.",
  },
};

"use client";

import { ArrowLeft, CheckCircle2, ShieldAlert, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Check, Problem, SolveReport, TraceabilityReport } from "@/lib/api";
import { fmt } from "@/lib/format";

import { DiagnosisPanel, InsightsPanel, WhatIfPanel } from "./analysis-panels";
import { type Flow, FlowDiagram } from "./flow-diagram";
import { OUTCOME } from "./outcome";
import { TraceabilityPanel } from "./traceability-panel";

const SCOPE_LABELS = {
  status: "Solver",
  model: "Against the model",
  problem: "Against your data",
} as const;

const CHECK_LABELS: Record<string, string> = {
  values_finite: "Every value is a finite number",
  plan_covers_allowed_pairs_only: "Only allowed pairs are used",
  plan_values_finite: "Every planned quantity is a finite number",
  plan_route_limits: "No negative or over-limit shipments",
  plan_supply_respected: "No source ships more than it has",
  plan_demand_met: "Every destination gets its demand",
  plan_whole_assignments: "Every assignment is all-or-nothing",
  plan_agent_capacity: "No agent is over capacity",
  plan_task_staffing: "Every task is staffed exactly",
  plan_objective_from_data: "Objective recomputed from your data",
  solver_status: "Solver reached an optimal solution",
  all_variables_reported: "Every variable has a value",
  variable_bounds: "All quantities within their bounds",
  integrality: "Whole-number values where required",
  constraints_satisfied: "Every constraint holds",
  objective_recomputed: "Objective recomputed independently",
  supply_covers_demand: "Total supply covers total demand",
  every_destination_reachable: "Every destination has a route in",
  inbound_capacity_covers_demand: "Route capacity can meet each demand",
  unbalanced_problem: "Supply and demand are balanced",
  capacity_covers_requirements: "Agent capacity covers all positions",
  enough_eligible_agents: "Every task has enough eligible agents",
};

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="gap-1 py-4">
      <CardContent className="space-y-1 px-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function Meter({ label, used, total }: { label: string; used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {fmt(used)} / {fmt(total)}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-primary/15"
        role="meter"
        aria-label={`${label} utilisation`}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function CheckRow({ check }: { check: Check }) {
  const warn = !check.passed && check.severity === "warning";
  const Icon = check.passed ? CheckCircle2 : warn ? TriangleAlert : XCircle;
  const color = check.passed
    ? "text-primary"
    : warn
      ? "text-amber-600 dark:text-amber-400"
      : "text-destructive";
  return (
    <li className="flex gap-3 py-2.5">
      <Icon className={`mt-0.5 size-4 shrink-0 ${color}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-sm">{CHECK_LABELS[check.name] ?? check.name}</p>
          <span className="sr-only">{check.passed ? "passed" : warn ? "warning" : "failed"}</span>
        </div>
        {check.detail && (
          <p className="font-mono text-xs break-words text-muted-foreground">{check.detail}</p>
        )}
      </div>
    </li>
  );
}

export function ResultsStep({
  report,
  problem,
  onBack,
  backLabel = "Model",
  actions,
  traceability,
}: {
  report: SolveReport;
  problem: Problem;
  onBack: () => void;
  backLabel?: string;
  /** Saved requirement traceability; absent for projects saved before it existed. */
  traceability?: TraceabilityReport | null;
  /** Extra buttons shown next to the verification badge (export, print, ...). */
  actions?: React.ReactNode;
}) {
  const { result, solution, stats, model } = report;
  const minimize = model.sense === "minimize";
  const transport = solution?.kind === "transportation" ? solution : null;
  const assign = solution?.kind === "assignment" ? solution : null;

  const flows: Flow[] = transport
    ? transport.shipments.map((s) => ({
        from: s.source,
        to: s.destination,
        amount: s.quantity,
        detail: [`${fmt(s.unit_cost)} per unit`, `${fmt(s.cost)} total`],
      }))
    : (assign?.assignments.map((a) => ({
        from: a.agent,
        to: a.task,
        amount: 1,
        detail: [`value ${fmt(a.value)}`],
      })) ?? []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft /> {backLabel}
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          {actions}
          {report.verified ? (
            <Badge
              className="gap-1.5 px-3 py-1 text-sm"
              title="Proven optimal for the approved model and re-checked against your data"
            >
              <ShieldCheck className="size-4" /> Plan verified
            </Badge>
          ) : (
            <Badge variant="destructive" className="gap-1.5 px-3 py-1 text-sm">
              <ShieldAlert className="size-4" /> {OUTCOME[report.outcome].badge}
            </Badge>
          )}
          {traceability && traceability.status !== "checked" && (
            <Badge
              variant={traceability.status === "unsupported" ? "destructive" : "secondary"}
              className="gap-1.5 px-3 py-1 text-sm"
              title="Whether the model matches the description; separate from plan verification"
            >
              <TriangleAlert className="size-4" />
              {traceability.status === "unsupported"
                ? "Request partly unsupported"
                : `Formulation: ${traceability.counts.unresolved} unresolved`}
            </Badge>
          )}
        </div>
      </div>

      {!solution ? (
        <Card>
          <CardHeader>
            <CardTitle>{OUTCOME[report.outcome].title}</CardTitle>
            <CardDescription>
              {OUTCOME[report.outcome].text}
              {result.message && <> ({result.message})</>}
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <>
          <section className="space-y-1">
            <p className="text-sm text-muted-foreground">
              {transport ? "Total cost" : minimize ? "Total cost" : "Total preference score"}
            </p>
            <p className="text-5xl font-semibold tracking-tight">{fmt(result.objective)}</p>
            <p className="text-sm text-muted-foreground">
              {minimize ? "Minimized" : "Maximized"} · {result.status} · {result.solver} in{" "}
              {fmt(result.wall_time_ms)} ms · {stats.variables} variables, {stats.constraints}{" "}
              constraints
            </p>
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            {transport && (
              <>
                <Stat
                  label="Units shipped"
                  value={fmt(transport.shipments.reduce((s, x) => s + x.quantity, 0))}
                />
                <Stat
                  label="Routes used"
                  value={`${transport.shipments.length}`}
                  sub={`of ${stats.variables} allowed`}
                />
                <Stat
                  label="Unused supply"
                  value={fmt(transport.sources.reduce((s, x) => s + x.unused, 0))}
                />
              </>
            )}
            {assign && (
              <>
                <Stat label="Assignments" value={`${assign.assignments.length}`} />
                <Stat
                  label="Unassigned agents"
                  value={`${assign.unassigned_agents.length}`}
                  sub={assign.unassigned_agents.join(", ") || undefined}
                />
                <Stat
                  label="Average value per assignment"
                  value={fmt(
                    assign.assignments.reduce((s, a) => s + a.value, 0) /
                      Math.max(assign.assignments.length, 1),
                  )}
                />
              </>
            )}
          </section>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {transport ? "Shipment plan" : "Assignment plan"}
              </CardTitle>
              <CardDescription>
                Link width is {transport ? "quantity shipped" : "one assignment"}. Hover for
                details.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FlowDiagram
                flows={flows}
                fromLabel={transport ? "Sources" : "Agents"}
                toLabel={transport ? "Destinations" : "Tasks"}
                unit={transport ? "units" : "assignment(s)"}
              />
            </CardContent>
          </Card>

          <div className="grid items-start gap-6 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle className="text-base">
                  {transport ? "Shipments" : "Assignments"}
                </CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs text-muted-foreground">
                    <tr className="border-b">
                      <th className="py-2 text-left font-medium">{transport ? "From" : "Agent"}</th>
                      <th className="py-2 text-left font-medium">{transport ? "To" : "Task"}</th>
                      {transport && <th className="py-2 text-right font-medium">Quantity</th>}
                      <th className="py-2 text-right font-medium">
                        {transport ? "Unit cost" : "Value"}
                      </th>
                      {transport && <th className="py-2 text-right font-medium">Cost</th>}
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {transport?.shipments.map((s) => (
                      <tr key={`${s.source}-${s.destination}`}>
                        <td className="py-2">{s.source}</td>
                        <td className="py-2">{s.destination}</td>
                        <td className="py-2 text-right font-mono tabular-nums">{fmt(s.quantity)}</td>
                        <td className="py-2 text-right font-mono tabular-nums">{fmt(s.unit_cost)}</td>
                        <td className="py-2 text-right font-mono tabular-nums">{fmt(s.cost)}</td>
                      </tr>
                    ))}
                    {assign?.assignments.map((a) => (
                      <tr key={`${a.agent}-${a.task}`}>
                        <td className="py-2">{a.agent}</td>
                        <td className="py-2">{a.task}</td>
                        <td className="py-2 text-right font-mono tabular-nums">{fmt(a.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t font-medium">
                      <td className="py-2" colSpan={transport ? 4 : 2}>
                        Total
                      </td>
                      <td className="py-2 text-right font-mono tabular-nums">
                        {fmt(result.objective)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </CardContent>
            </Card>

            {transport && (
              <Card className="lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-base">Source utilisation</CardTitle>
                  <CardDescription>Shipped versus available supply.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {transport.sources.map((s) => (
                    <Meter key={s.id} label={s.id} used={s.shipped} total={s.supply} />
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}

      {report.diagnosis && <DiagnosisPanel diagnosis={report.diagnosis} />}
      {traceability && <TraceabilityPanel report={traceability} />}
      {solution && <InsightsPanel report={report} />}
      {solution && <WhatIfPanel problem={problem} base={report} />}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Data checks</CardTitle>
            <CardDescription>Run on your data before solving.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {report.prechecks.map((c) => (
                <CheckRow key={c.name} check={c} />
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Solution checks</CardTitle>
            <CardDescription>
              Re-checked without trusting the solver: against the model, then against your data
              directly (which also catches a bug in how the model was built). Tolerance 1e-6,
              relative to each quantity.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {(["status", "model", "problem"] as const).map((scope) => {
              const checks = report.verification.checks.filter((c) => c.scope === scope);
              if (!checks.length) return null;
              return (
                <section key={scope}>
                  <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    {SCOPE_LABELS[scope]}
                  </h4>
                  <ul className="divide-y">
                    {checks.map((c) => (
                      <CheckRow key={c.name} check={c} />
                    ))}
                  </ul>
                </section>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

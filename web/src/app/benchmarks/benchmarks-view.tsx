"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type BenchmarkSummary, client, unwrap } from "@/lib/api";

const MODE_LABEL: Record<string, string> = {
  direct: "LLM answers directly",
  "no-verify": "LLM model, no verification",
  full: "OptiAgent (verified)",
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

function Bars({
  rows,
  label,
}: {
  rows: { name: string; value: number; highlight?: boolean }[];
  label: string;
}) {
  return (
    <figure className="space-y-3" aria-label={label}>
      {rows.map((r) => (
        <div key={r.name} className="grid grid-cols-[1fr_3rem] items-center gap-x-3 gap-y-1 text-sm sm:grid-cols-[16rem_1fr_3rem]">
          <span className={`col-span-2 sm:col-span-1 ${r.highlight ? "font-medium" : "text-muted-foreground"}`}>{r.name}</span>
          <div className="h-3 overflow-hidden rounded-full bg-primary/10">
            <div
              className={`h-full rounded-full ${r.highlight ? "bg-primary" : "bg-primary/45"}`}
              style={{ width: `${Math.max(r.value * 100, 1)}%` }}
            />
          </div>
          <span className="text-right font-mono tabular-nums">{pct(r.value)}</span>
        </div>
      ))}
    </figure>
  );
}

type Verification = NonNullable<BenchmarkSummary["verification"]>;
type Rate = Verification["builder_faults"]["either"];

function RateCell({ r }: { r: Rate }) {
  return (
    <td className="py-2 text-right font-mono tabular-nums" title={`95% CI ${pct(r.low)}–${pct(r.high)}`}>
      {r.n ? pct(r.k / r.n) : "—"}{" "}
      <span className="text-xs text-muted-foreground">
        ({r.k}/{r.n})
      </span>
    </td>
  );
}

function VerificationCard({ v }: { v: Verification }) {
  const b = v.builder_faults;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Deterministic verification benchmark</CardTitle>
        <CardDescription>
          No AI involved. Recall: broken models flagged. False-positive rate: correct models
          flagged. The two baselines show why both numbers matter. Hover a rate for its 95%
          interval.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="py-2 text-left font-medium">Dataset · detector</th>
              <th className="py-2 text-right font-medium">Recall</th>
              <th className="py-2 text-right font-medium">False-positive rate</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {v.formulation.flatMap((f) =>
              f.scores.map((d) => (
                <tr key={`${f.dataset}-${d.detector}`}>
                  <td className="py-2">
                    <span className="text-muted-foreground">{f.dataset} · </span>
                    <span className={d.detector.includes("baseline") ? "text-muted-foreground" : "font-medium"}>
                      {d.detector}
                    </span>
                  </td>
                  <RateCell r={d.recall} />
                  <RateCell r={d.false_positive_rate} />
                </tr>
              )),
            )}
          </tbody>
        </table>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-1 rounded-lg border p-4 text-sm">
            <p className="font-medium">Model-builder faults</p>
            <p className="text-muted-foreground">
              {b.harmful} harmful faults. Checks against the model caught{" "}
              <span className="font-mono text-foreground">{b.model_checks.k}</span>; checks
              against your data (with a duality certificate) caught{" "}
              <span className="font-mono text-foreground">{b.problem_checks.k}</span>.
            </p>
          </div>
          <div className="space-y-1 rounded-lg border p-4 text-sm">
            <p className="font-medium">Malformed data</p>
            <p className="text-muted-foreground">
              <span className="font-mono text-foreground">
                {v.malformed_data.detected.k}/{v.malformed_data.detected.n}
              </span>{" "}
              corrupted cells reported with the exact cell;{" "}
              {v.malformed_data.clean_false_alarms.k} false alarms on clean data.
            </p>
          </div>
          <div className="space-y-1 rounded-lg border p-4 text-sm">
            <p className="font-medium">Out-of-scope requests</p>
            <p className="text-muted-foreground">
              Held-out set: {v.scope_held_out.recall.k}/{v.scope_held_out.recall.n} flagged,{" "}
              {v.scope_held_out.false_positive_rate.k}/{v.scope_held_out.false_positive_rate.n}{" "}
              false alarms. (Tuning set: {v.scope_tuning.recall.k}/{v.scope_tuning.recall.n}, optimistic.)
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const DETECTORS = [
  ["llm", "AI analysis"],
  ["patterns", "Patterns"],
  ["either", "Either"],
] as const;

function ScopeCard({ results }: { results: NonNullable<BenchmarkSummary["scope_llm"]> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Out-of-scope requests: AI vs patterns</CardTitle>
        <CardDescription>
          Recall: unsupported requests flagged. False alarms: ordinary requests wrongly rejected.
          scope_v2 was never used for tuning; the problem sets are the supported problems above.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="py-2 text-left font-medium">Set · model · detector</th>
              <th className="py-2 text-right font-medium">Recall</th>
              <th className="py-2 text-right font-medium">False alarms</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {results.flatMap((r) =>
              DETECTORS.map(([key, name]) => (
                <tr key={`${r.dataset}-${r.model}-${key}`}>
                  <td className="py-2">
                    <span className="text-muted-foreground">
                      {r.dataset} · {r.model} ·{" "}
                    </span>
                    <span className={key === "either" ? "font-medium" : ""}>{name}</span>
                  </td>
                  <RateCell r={r[key].recall} />
                  <RateCell r={r[key].false_positive_rate} />
                </tr>
              )),
            )}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function Results({ s }: { s: BenchmarkSummary }) {
  const label = (m: { mode: string; model: string }) =>
    `${MODE_LABEL[m.mode] ?? m.mode} · ${m.model}`;
  return (
    <div className="space-y-6">
      {s.modes.length > 0 ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Silent errors</CardTitle>
              <CardDescription>
                Share of problems that end with a wrong answer and no warning. Lower is better.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Bars
                label="Silent error rate by approach"
                rows={s.modes.map((m) => ({
                  name: label(m),
                  value: m.silent_error_rate,
                  highlight: m.mode === "full",
                }))}
              />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Correct optimum</CardTitle>
              <CardDescription>Share of problems solved to the true optimum.</CardDescription>
            </CardHeader>
            <CardContent>
              <Bars
                label="Objective accuracy by approach"
                rows={s.modes.map((m) => ({
                  name: label(m),
                  value: m.objective_accuracy,
                  highlight: m.mode === "full",
                }))}
              />
            </CardContent>
          </Card>
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No end-to-end runs yet</CardTitle>
            <CardDescription>
              Run <code className="font-mono">python -m optiagent_eval.run --mode full</code>, then{" "}
              <code className="font-mono">python -m optiagent_eval.report</code>.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {s.modes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">All metrics</CardTitle>
            <CardDescription>
              {s.modes[0].supported} supported problems per run; models: {[...new Set(s.modes.map((m) => m.model))].join(", ")}.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b">
                  {["Approach", "Correct optimum", "Exact model", "Wrong models", "Caught before approval", "False alarms", "Silent errors", "LLM calls", "Seconds / problem"].map((h, i) => (
                    <th key={h} className={`py-2 font-medium ${i === 0 ? "text-left" : "text-right"}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {s.modes.map((m) => {
                  const direct = m.mode === "direct";
                  return (
                    <tr key={m.file}>
                      <td className="py-2">{label(m)}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{pct(m.objective_accuracy)}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{direct ? "—" : pct(m.structure_exact_rate)}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{direct ? "—" : m.wrong_models}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{m.mode === "full" ? `${m.audit_caught}/${m.wrong_models}` : "—"}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{m.mode === "full" ? m.audit_false_alarms : "—"}</td>
                      <td className="py-2 text-right font-mono font-medium tabular-nums">{pct(m.silent_error_rate)}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{m.mean_llm_calls.toFixed(1)}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{Math.round(m.mean_latency_s)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {s.modes
              .filter((m) => m.mode !== "direct" && Object.keys(m.diff_categories).length > 0)
              .map((m) => (
                <div key={m.file} className="mt-4 text-sm">
                  <p className="font-medium">Model errors made by {label(m)}</p>
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {Object.entries(m.diff_categories).map(([k, v]) => (
                      <li key={k} className="rounded-md bg-muted px-2 py-0.5 font-mono text-xs">
                        {k.replaceAll("_", " ")}: {v}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Formulation audit on injected errors</CardTitle>
          <CardDescription>
            Each correct model is broken one way at a time. The audit must flag every broken model
            and none of the correct ones.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {s.audit.map((a) => (
            <div key={a.dataset} className="space-y-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-medium">{a.dataset}</p>
                <p className="text-sm text-muted-foreground">
                  <span className="font-mono text-foreground">{a.detected}/{a.injected}</span> caught (
                  {pct(a.detected / Math.max(a.injected, 1))}) ·{" "}
                  <span className="font-mono text-foreground">{a.false_alarms}/{a.problems}</span> false alarms
                </p>
              </div>
              <Bars
                label={`Detection by error type, ${a.dataset}`}
                rows={Object.entries(a.categories).map(([k, [d, n]]) => ({
                  name: k.replaceAll("_", " "),
                  value: n ? d / n : 0,
                  highlight: d === n,
                }))}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      {s.verification && <VerificationCard v={s.verification} />}
      {s.scope_llm && s.scope_llm.length > 0 && <ScopeCard results={s.scope_llm} />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Info className="size-4" /> How to read these numbers
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
            {s.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            Generated {new Date(s.generated_at).toLocaleString()}.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export function BenchmarksView() {
  const summary = useQuery({
    queryKey: ["benchmarks"],
    queryFn: () => unwrap(client.GET("/api/v1/benchmarks")),
    retry: false,
  });
  if (summary.isPending) {
    return (
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
    );
  }
  if (summary.error) {
    return <p className="text-sm text-destructive">{summary.error.message}</p>;
  }
  return <Results s={summary.data} />;
}

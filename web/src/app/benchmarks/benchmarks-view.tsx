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
        <div key={r.name} className="grid grid-cols-[12rem_1fr_3rem] items-center gap-3 text-sm">
          <span className={r.highlight ? "font-medium" : "text-muted-foreground"}>{r.name}</span>
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

function Results({ s }: { s: BenchmarkSummary }) {
  const full = s.modes.find((m) => m.mode === "full");
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
                  name: MODE_LABEL[m.mode] ?? m.mode,
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
                  name: MODE_LABEL[m.mode] ?? m.mode,
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
                  {["Approach", "Correct optimum", "Exact model", "Wrong models", "Caught by audit", "Audit false alarms", "Silent errors", "LLM calls", "Seconds / problem"].map((h, i) => (
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
                    <tr key={m.mode}>
                      <td className="py-2">{MODE_LABEL[m.mode] ?? m.mode}</td>
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
            {full && Object.keys(full.diff_categories).length > 0 && (
              <div className="mt-4 text-sm">
                <p className="font-medium">Where the verified pipeline still got the model wrong</p>
                <ul className="mt-1 flex flex-wrap gap-2">
                  {Object.entries(full.diff_categories).map(([k, v]) => (
                    <li key={k} className="rounded-md bg-muted px-2 py-0.5 font-mono text-xs">
                      {k.replaceAll("_", " ")}: {v}
                    </li>
                  ))}
                </ul>
              </div>
            )}
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

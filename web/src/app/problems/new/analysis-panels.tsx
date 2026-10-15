"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  Gauge,
  Lightbulb,
  Loader2,
  Lock,
  PackageOpen,
  RotateCcw,
  Shuffle,
  SlidersHorizontal,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { client, type Diagnosis, type Insight, type Problem, type SolveReport, unwrap } from "@/lib/api";
import { fmt } from "@/lib/format";

import { OUTCOME } from "./outcome";

// --------------------------------------------------------------------------- insights

const GROUPS: { title: string; kinds: Insight["kind"][]; icon: typeof Lock; limit: number }[] = [
  { title: "Equally good alternatives", kinds: ["alternative_optimum"], icon: Shuffle, limit: 4 },
  { title: "What limits the plan", kinds: ["binding", "limit"], icon: Lock, limit: 6 },
  { title: "Options not used", kinds: ["unused_option"], icon: Lightbulb, limit: 5 },
  { title: "Spare capacity", kinds: ["slack"], icon: PackageOpen, limit: 5 },
  { title: "How far costs can move", kinds: ["cost_range"], icon: Gauge, limit: 4 },
];

export function InsightsPanel({ report }: { report: SolveReport }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  if (!report.sensitivity?.available || report.insights.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">What drives this plan</CardTitle>
        <CardDescription>
          One-unit effects and route-limit effects are exact: each was re-solved. Cost ranges are
          local solver ranges that assume everything else stays the same; they are not forecasts.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {report.sensitivity.degenerate && (
          <p className="flex gap-2 rounded-md bg-muted/50 p-3 text-xs text-muted-foreground">
            <TriangleAlert className="size-4 shrink-0" />
            This plan sits on a corner of the feasible region (degenerate), so some effects differ
            depending on whether a number goes up or down. Both directions are shown.
          </p>
        )}
        <div className="grid gap-6 md:grid-cols-2">
          {GROUPS.map((g) => {
            const items = report.insights.filter((i) => g.kinds.includes(i.kind));
            if (items.length === 0) return null;
            const open = expanded[g.title];
            const shown = open ? items : items.slice(0, g.limit);
            return (
              <section key={g.title} className="space-y-2">
                <h4 className="flex items-center gap-2 text-sm font-medium">
                  <g.icon className="size-4 text-primary" /> {g.title}
                  <Badge variant="secondary">{items.length}</Badge>
                </h4>
                <ul className="space-y-2 text-sm">
                  {shown.map((i) => (
                    <li key={i.source} className="rounded-md border p-3">
                      <p className="font-medium">{i.title}</p>
                      <p className="text-muted-foreground">{i.text}</p>
                    </li>
                  ))}
                </ul>
                {items.length > g.limit && (
                  <button
                    type="button"
                    className="text-xs text-primary hover:underline"
                    onClick={() => setExpanded((e) => ({ ...e, [g.title]: !open }))}
                  >
                    {open ? "Show fewer" : `Show all ${items.length}`}
                  </button>
                )}
              </section>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- diagnosis

export function DiagnosisPanel({ diagnosis }: { diagnosis: Diagnosis }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Why there is no solution</CardTitle>
        <CardDescription>{diagnosis.explanation}</CardDescription>
      </CardHeader>
      {diagnosis.shortfalls.length > 0 && (
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 text-left font-medium">Where</th>
                <th className="py-2 text-right font-medium">Required</th>
                <th className="py-2 text-right font-medium">Achievable</th>
                <th className="py-2 text-right font-medium">Short by</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {diagnosis.shortfalls.map((s) => (
                <tr key={s.constraint}>
                  <td className="py-2">{s.id}</td>
                  <td className="py-2 text-right font-mono tabular-nums">{fmt(s.required)}</td>
                  <td className="py-2 text-right font-mono tabular-nums">{fmt(s.achievable)}</td>
                  <td className="py-2 text-right font-mono text-destructive tabular-nums">
                    {fmt(s.shortfall)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted-foreground">
            Raise supply, lower demand or relax limits by at least the shortfall, then solve again.
          </p>
        </CardContent>
      )}
      <CardContent className="pt-0">
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer text-primary">How this was computed</summary>
          <p className="mt-2">{diagnosis.method}</p>
        </details>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- what-if

interface Parameter {
  key: string;
  group: string;
  label: string;
  value: number;
  apply: (p: Problem, v: number) => Problem;
}

function parameters(problem: Problem): Parameter[] {
  if (problem.kind === "transportation") {
    return [
      ...problem.sources.map((s) => ({
        key: `supply:${s.id}`, group: "Supply", label: s.id, value: s.supply,
        apply: (p: Problem, v: number) => p.kind === "transportation"
          ? { ...p, sources: p.sources.map((x) => (x.id === s.id ? { ...x, supply: v } : x)) } : p,
      })),
      ...problem.destinations.map((d) => ({
        key: `demand:${d.id}`, group: "Demand", label: d.id, value: d.demand,
        apply: (p: Problem, v: number) => p.kind === "transportation"
          ? { ...p, destinations: p.destinations.map((x) => (x.id === d.id ? { ...x, demand: v } : x)) } : p,
      })),
      ...problem.routes.map((r) => ({
        key: `cost:${r.source}:${r.destination}`, group: "Cost per unit",
        label: `${r.source} → ${r.destination}`, value: r.cost,
        apply: (p: Problem, v: number) => p.kind === "transportation"
          ? { ...p, routes: p.routes.map((x) => x.source === r.source && x.destination === r.destination ? { ...x, cost: v } : x) } : p,
      })),
      ...problem.routes.filter((r) => r.capacity != null).map((r) => ({
        key: `cap:${r.source}:${r.destination}`, group: "Route limit",
        label: `${r.source} → ${r.destination}`, value: r.capacity as number,
        apply: (p: Problem, v: number) => p.kind === "transportation"
          ? { ...p, routes: p.routes.map((x) => x.source === r.source && x.destination === r.destination ? { ...x, capacity: v } : x) } : p,
      })),
    ]; // prettier-ignore
  }
  return [
    ...problem.pairings.map((x) => ({
      key: `value:${x.agent}:${x.task}`, group: "Value", label: `${x.agent} → ${x.task}`, value: x.value,
      apply: (p: Problem, v: number) => p.kind === "assignment"
        ? { ...p, pairings: p.pairings.map((y) => y.agent === x.agent && y.task === x.task ? { ...y, value: v } : y) } : p,
    })),
    ...problem.agents.map((a) => ({
      key: `cap:${a.id}`, group: "Agent capacity", label: a.id, value: a.capacity ?? 1,
      apply: (p: Problem, v: number) => p.kind === "assignment"
        ? { ...p, agents: p.agents.map((y) => (y.id === a.id ? { ...y, capacity: Math.round(v) } : y)) } : p,
    })),
    ...problem.tasks.map((t) => ({
      key: `req:${t.id}`, group: "Agents needed", label: t.id, value: t.required ?? 1,
      apply: (p: Problem, v: number) => p.kind === "assignment"
        ? { ...p, tasks: p.tasks.map((y) => (y.id === t.id ? { ...y, required: Math.round(v) } : y)) } : p,
    })),
  ]; // prettier-ignore
}

function flows(report: SolveReport): Map<string, number> {
  const s = report.solution;
  if (!s) return new Map();
  if (s.kind === "transportation") {
    return new Map(s.shipments.map((x) => [`${x.source} → ${x.destination}`, x.quantity]));
  }
  return new Map(s.assignments.map((x) => [`${x.agent} → ${x.task}`, 1]));
}

export function WhatIfPanel({ problem, base }: { problem: Problem; base: SolveReport }) {
  const params = useMemo(() => parameters(problem), [problem]);
  const [key, setKey] = useState(params[0]?.key ?? "");
  const param = params.find((p) => p.key === key);
  const [value, setValue] = useState(param ? String(param.value) : "");

  const run = useMutation({
    mutationFn: (changed: Problem) => unwrap(client.POST("/api/v1/solve", { body: changed })),
  });

  const groups = [...new Set(params.map((p) => p.group))];
  const number = Number(value);
  const valid = value.trim() !== "" && Number.isFinite(number) && number >= 0;
  const result = run.data;

  const diff = useMemo(() => {
    if (!result) return [];
    const before = flows(base);
    const after = flows(result);
    const keys = new Set([...before.keys(), ...after.keys()]);
    return [...keys]
      .map((k) => ({ k, before: before.get(k) ?? 0, after: after.get(k) ?? 0 }))
      .filter((d) => Math.abs(d.after - d.before) > 1e-9);
  }, [base, result]);

  const baseObj = base.result.objective ?? 0;
  const newObj = result?.result.objective;
  const delta = newObj != null ? newObj - baseObj : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <SlidersHorizontal className="size-4" /> What if…
        </CardTitle>
        <CardDescription>Change one number and re-solve. Your model is not changed.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid items-end gap-3 sm:grid-cols-[1fr_9rem_auto]">
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Number to change</Label>
            <Select
              value={key}
              onValueChange={(k) => {
                setKey(k);
                const p = params.find((x) => x.key === k);
                setValue(p ? String(p.value) : "");
                run.reset();
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {groups.map((g) => (
                  <SelectGroup key={g}>
                    <SelectLabel>{g}</SelectLabel>
                    {params
                      .filter((p) => p.group === g)
                      .map((p) => (
                        <SelectItem key={p.key} value={p.key}>
                          {p.label} <span className="text-muted-foreground">({fmt(p.value)})</span>
                        </SelectItem>
                      ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="whatif-value" className="text-xs text-muted-foreground">
              New value
            </Label>
            <Input
              id="whatif-value"
              type="number"
              min={0}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="font-mono"
            />
          </div>
          <Button
            disabled={!param || !valid || run.isPending}
            onClick={() => param && run.mutate(param.apply(problem, number))}
          >
            {run.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Re-solve
          </Button>
        </div>

        {run.error && <p className="text-sm text-destructive">{run.error.message}</p>}

        {result && param && (
          <div className="space-y-4 rounded-lg border p-4">
            <p className="text-sm">
              {param.group} <span className="font-medium">{param.label}</span>: {fmt(param.value)} →{" "}
              <span className="font-medium">{fmt(number)}</span>
            </p>
            {result.outcome === "verified_optimal" && newObj != null && delta != null ? (
              <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
                <p className="text-2xl font-semibold tracking-tight">{fmt(newObj)}</p>
                <p
                  className={`flex items-center gap-1 text-sm ${
                    Math.abs(delta) < 1e-9
                      ? "text-muted-foreground"
                      : (delta < 0) === (problem.sense === "minimize")
                        ? "text-primary"
                        : "text-destructive"
                  }`}
                >
                  {delta > 0 ? <ArrowUpRight className="size-4" /> : delta < 0 ? <ArrowDownRight className="size-4" /> : null}
                  {delta >= 0 ? "+" : ""}
                  {fmt(delta)} vs {fmt(baseObj)}
                  {baseObj !== 0 && ` (${delta >= 0 ? "+" : ""}${fmt((delta / Math.abs(baseObj)) * 100)}%)`}
                </p>
                <Badge>Plan verified</Badge>
              </div>
            ) : (
              <Alert variant="destructive">
                <AlertTitle>{OUTCOME[result.outcome].title}</AlertTitle>
                <AlertDescription>
                  {result.diagnosis?.explanation ?? OUTCOME[result.outcome].text}
                </AlertDescription>
              </Alert>
            )}
            <p className="text-xs text-muted-foreground">
              Scenario only: the approved model and the saved project are unchanged. Baseline{" "}
              {fmt(baseObj)}; only {param.label} changed.
            </p>
            {diff.length > 0 && (
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr className="border-b">
                    <th className="py-1.5 text-left font-medium">Changed</th>
                    <th className="py-1.5 text-right font-medium">Before</th>
                    <th className="py-1.5 text-right font-medium">After</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {diff.map((d) => (
                    <tr key={d.k}>
                      <td className="py-1.5">{d.k}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{fmt(d.before)}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{fmt(d.after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {result.outcome === "verified_optimal" && diff.length === 0 && (
              <p className="text-sm text-muted-foreground">The plan itself does not change.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

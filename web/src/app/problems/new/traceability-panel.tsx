"use client";

import { Ban, CheckCircle2, CircleDot, HelpCircle, ListChecks, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { Provenance, TraceabilityReport, TraceRow } from "@/lib/api";
import { fmt } from "@/lib/format";

type Status = TraceRow["status"];

const STATUS: Record<Status, { icon: typeof CheckCircle2; className: string; label: string; help: string }> = {
  verified: {
    icon: CheckCircle2,
    className: "text-primary",
    label: "Verified",
    help: "A deterministic check tied this to the model exactly.",
  },
  represented: {
    icon: CircleDot,
    className: "text-muted-foreground",
    label: "Represented",
    help: "In the model, but no deterministic check confirms the link.",
  },
  unresolved: {
    icon: HelpCircle,
    className: "text-amber-600 dark:text-amber-400",
    label: "Unresolved",
    help: "Missing, contradicted, ambiguous or unchecked. Needs you.",
  },
  unsupported: {
    icon: Ban,
    className: "text-destructive",
    label: "Unsupported",
    help: "The description asks for something this model cannot express. It was not modelled.",
  },
};

const OVERALL = {
  checked: { label: "Traced", variant: "default" },
  needs_review: { label: "Needs review", variant: "secondary" },
  unsupported: { label: "Unsupported request", variant: "destructive" },
} as const;

function StatusIcon({ status }: { status: Status }) {
  const s = STATUS[status];
  return <s.icon className={`mt-0.5 size-4 shrink-0 ${s.className}`} aria-label={s.label} />;
}

function RequirementItem({ row }: { row: TraceRow }) {
  return (
    <li className="flex gap-2 text-sm">
      <StatusIcon status={row.status} />
      <div className="min-w-0 space-y-0.5">
        <p>{row.interpretation}</p>
        <p className="font-mono text-xs break-words text-muted-foreground">“{row.requirement}”</p>
        {row.model_element && (
          <p className="text-xs text-muted-foreground">Model: {row.model_element}</p>
        )}
        {row.note && <p className="text-xs">{row.note}</p>}
      </div>
    </li>
  );
}

function ProvenanceItem({ p }: { p: Provenance }) {
  return (
    <li className="flex gap-2 text-sm">
      <StatusIcon status={p.status} />
      <div className="min-w-0">
        <p>
          {p.parameter} = <span className="font-mono">{fmt(p.value)}</span>
        </p>
        {p.evidence && <p className="text-xs break-words text-muted-foreground">{p.evidence}</p>}
      </div>
    </li>
  );
}

export function TraceabilityPanel({
  report,
  loading,
}: {
  report?: TraceabilityReport;
  loading?: boolean;
}) {
  if (loading || !report) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="size-4 animate-spin text-muted-foreground" /> Requirement traceability
          </CardTitle>
          <CardDescription>Linking each statement and number to the model…</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const open = (s: Status) => s === "unresolved" || s === "unsupported";
  const openRows = report.requirements.filter((r) => open(r.status));
  const openParams = report.provenance.filter((p) => open(p.status));
  const overall = OVERALL[report.status];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks className="size-4" /> Requirement traceability
          <Badge variant={overall.variant} className="ml-auto">
            {overall.label}
          </Badge>
        </CardTitle>
        <CardDescription>
          Does the model say what you said? Checked by code, separately from solving.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          {(Object.keys(STATUS) as Status[]).map((s) => (
            <div key={s} className="rounded-md border px-2 py-1.5" title={STATUS[s].help}>
              <dt className="text-muted-foreground">{STATUS[s].label}</dt>
              <dd className="text-base font-medium tabular-nums">{report.counts[s] ?? 0}</dd>
            </div>
          ))}
        </dl>

        {openRows.length + openParams.length > 0 && (
          <ul className="space-y-3">
            {openRows.map((r, i) => (
              <RequirementItem key={`r${i}`} row={r} />
            ))}
            {openParams.map((p) => (
              <ProvenanceItem key={p.parameter} p={p} />
            ))}
          </ul>
        )}

        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-primary">
            All requirements ({report.requirements.length})
          </summary>
          <ul className="mt-2 space-y-3">
            {report.requirements.map((r, i) => (
              <RequirementItem key={i} row={r} />
            ))}
          </ul>
        </details>
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-primary">
            Where each number comes from ({report.provenance.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {report.provenance.map((p) => (
              <ProvenanceItem key={p.parameter} p={p} />
            ))}
          </ul>
        </details>

        <ul className="space-y-1 border-t pt-3 text-xs text-muted-foreground">
          {report.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

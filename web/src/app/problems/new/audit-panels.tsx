"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  CircleSlash,
  ClipboardCheck,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  XCircle,
} from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type AuditReport, client, type Problem, type RequirementCheck, unwrap } from "@/lib/api";

const CHECK_NAMES: Record<string, string> = {
  text_cross_check: "Values match your description",
  route_limit: "Route limits match",
  unused_numbers: "Every number you gave is used",
  wording: "Objective and wording agree",
  structure: "Every item can take part",
  sanity: "Solver sanity tests",
};

const SEVERITY = {
  error: { icon: XCircle, className: "text-destructive", label: "error" },
  warning: { icon: TriangleAlert, className: "text-amber-600 dark:text-amber-400", label: "warning" },
  info: { icon: AlertCircle, className: "text-muted-foreground", label: "note" },
} as const;

export function useAudit(problem: Problem, text: string | undefined) {
  return useQuery({
    queryKey: ["audit", problem, text ?? null],
    queryFn: () =>
      unwrap(client.POST("/api/v1/audit", { body: { problem, text: text?.trim() || null } })),
  });
}

export function AuditPanel({ report, loading }: { report?: AuditReport; loading: boolean }) {
  const issues = report?.findings.filter((f) => f.severity !== "info") ?? [];
  const failed = new Set(issues.map((f) => f.check));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {loading || !report ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          ) : report.passed && issues.length === 0 ? (
            <ShieldCheck className="size-4 text-primary" />
          ) : (
            <ShieldAlert
              className={`size-4 ${report.passed ? "text-amber-600 dark:text-amber-400" : "text-destructive"}`}
            />
          )}
          Formulation audit
        </CardTitle>
        <CardDescription>
          {!report
            ? "Checking the model against your description…"
            : issues.length === 0
              ? `All ${report.checks_run.length} checks passed.`
              : `${issues.length} issue(s) to review before solving.`}
        </CardDescription>
      </CardHeader>
      {report && (
        <CardContent className="space-y-4">
          {issues.length > 0 && (
            <ul className="space-y-3">
              {issues.map((f, i) => {
                const s = SEVERITY[f.severity];
                return (
                  <li key={i} className="flex gap-2 text-sm">
                    <s.icon className={`mt-0.5 size-4 shrink-0 ${s.className}`} />
                    <div className="min-w-0">
                      <p>
                        <span className="sr-only">{s.label}: </span>
                        {f.message}
                      </p>
                      {f.evidence && (
                        <p className="mt-0.5 font-mono text-xs break-words text-muted-foreground">
                          “{f.evidence}”
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <ul className="grid gap-1.5 text-xs text-muted-foreground">
            {report.checks_run.map((c) => (
              <li key={c} className="flex items-center gap-2">
                {failed.has(c) ? (
                  <XCircle className="size-3.5 text-destructive" />
                ) : (
                  <CheckCircle2 className="size-3.5 text-primary" />
                )}
                {CHECK_NAMES[c] ?? c}
              </li>
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  );
}

const STATUS = {
  covered: { icon: CheckCircle2, className: "text-primary", label: "Covered" },
  missing: { icon: XCircle, className: "text-destructive", label: "Missing" },
  contradicted: { icon: XCircle, className: "text-destructive", label: "Contradicted" },
  not_applicable: { icon: CircleSlash, className: "text-muted-foreground", label: "Background" },
} as const;

/** The AI requirement review. Shared by key, so several components reuse one request. */
export function useReview(requirements: string[], problem: Problem) {
  return useQuery({
    queryKey: ["review", requirements, problem],
    queryFn: () =>
      unwrap(client.POST("/api/v1/agent/review", { body: { requirements, problem } })),
    retry: false,
    enabled: requirements.length > 0,
  });
}

export function RequirementsPanel({
  requirements,
  problem,
}: {
  requirements: string[];
  problem: Problem;
}) {
  const review = useReview(requirements, problem);
  const checks = new Map<string, RequirementCheck>(
    review.data?.review.checks.map((c) => [c.requirement, c]) ?? [],
  );
  const problems = review.data?.review.checks.filter(
    (c) => c.status === "missing" || c.status === "contradicted",
  ).length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ClipboardCheck className="size-4" /> Your requirements
        </CardTitle>
        <CardDescription>
          {review.isPending
            ? "An independent AI reading is checking each one against the model…"
            : review.error
              ? "Automatic check unavailable. Check each one against the model yourself."
              : problems
                ? `${problems} requirement(s) may not be in the model.`
                : "The AI found each one in the model. This is an opinion, not a proof."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ol className="space-y-2 text-sm">
          {requirements.map((r) => {
            const c = checks.get(r);
            const s = c ? STATUS[c.status] : null;
            return (
              <li key={r} className="flex gap-2">
                {review.isPending ? (
                  <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-muted-foreground" />
                ) : s ? (
                  <s.icon className={`mt-0.5 size-4 shrink-0 ${s.className}`} aria-label={s.label} />
                ) : (
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
                )}
                <div className="min-w-0">
                  <p>{r}</p>
                  {c && (c.status === "missing" || c.status === "contradicted") && c.reason && (
                    <p className="text-xs text-muted-foreground">{c.reason}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
        {review.data && review.data.review.unexplained.length > 0 && (
          <div className="rounded-md bg-muted/50 p-3 text-xs">
            <p className="font-medium">In the model but not asked for:</p>
            <ul className="mt-1 list-disc pl-4 text-muted-foreground">
              {review.data.review.unexplained.map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

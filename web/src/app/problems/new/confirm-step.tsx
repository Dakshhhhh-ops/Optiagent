"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  ArrowLeft,
  Cpu,
  Info,
  Loader2,
  Play,
  TriangleAlert,
} from "lucide-react";

import { Tex } from "@/components/tex";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  client,
  type DataIssue,
  type Formulation,
  type Mapping,
  type Problem,
  type Project,
  type Trace,
  type Ungrounded,
  unwrap,
} from "@/lib/api";
import { fmt } from "@/lib/format";

import { AuditPanel, RequirementsPanel, useAudit, useReview } from "./audit-panels";
import { TraceabilityPanel } from "./traceability-panel";

export interface Candidate {
  problem: Problem;
  source: "ai" | "manual";
  requirements?: string[];
  ungrounded?: Ungrounded[];
  issues?: DataIssue[];
  trace?: Trace;
  /** The user's description, used by the audit. */
  text?: string;
  datasetId?: string | null;
  /** How the problem was read from the dataset; the server re-checks it. */
  mapping?: Mapping | null;
}

const PREVIEW_ITEMS = 4;
const SET_PREVIEW = 8;

function ConstraintCard({ group }: { group: Formulation["constraints"][number] }) {
  const [expanded, setExpanded] = useState(false);
  const items = expanded ? group.items : group.items.slice(0, PREVIEW_ITEMS);
  return (
    <div className="rounded-lg border">
      <div className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <span className="font-medium">{group.name}</span>
          <Badge variant="secondary">{group.items.length}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{group.english}</p>
        <Tex block>{group.latex}</Tex>
      </div>
      <div className="border-t px-4 py-3 text-sm">
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        {group.items.length > PREVIEW_ITEMS && (
          <button
            type="button"
            className="mt-2 text-xs text-primary hover:underline"
            onClick={() => setExpanded((e) => !e)}
          >
            {expanded ? "Show fewer" : `Show all ${group.items.length}`}
          </button>
        )}
      </div>
    </div>
  );
}

export function ConfirmStep({
  candidate,
  onBack,
  onSaved,
}: {
  candidate: Candidate;
  onBack: () => void;
  onSaved: (project: Project) => void;
}) {
  const { problem, requirements = [], ungrounded = [], issues = [], trace, text } = candidate;
  const audit = useAudit(problem, text);
  const auditErrors = audit.data?.findings.filter((x) => x.severity === "error").length ?? 0;
  const review = useReview(requirements, problem);
  const aiReview = review.data?.review ?? null;
  const traceBody = {
    problem,
    text: text?.trim() || null,
    requirements,
    review: aiReview,
    dataset_id: candidate.datasetId ?? null,
    mapping: candidate.mapping ?? null,
  };
  const traceability = useQuery({
    queryKey: ["traceability", traceBody],
    queryFn: () => unwrap(client.POST("/api/v1/traceability", { body: traceBody })),
    // Wait for the AI review (if any) so its flags are included; it never blocks on failure.
    enabled: requirements.length === 0 || !review.isPending,
  });
  const openItems =
    (traceability.data?.counts.unresolved ?? 0) + (traceability.data?.counts.unsupported ?? 0);
  const unsupported = traceability.data?.status === "unsupported";
  const blockers = auditErrors + openItems;

  const formulation = useQuery({
    queryKey: ["formulation", problem],
    queryFn: () => unwrap(client.POST("/api/v1/formulation", { body: problem })),
  });

  const solve = useMutation({
    // Saving a project solves it on the server; the project page then shows the results.
    mutationFn: () =>
      unwrap(
        client.POST("/api/v1/projects", {
          body: {
            problem,
            source: candidate.source,
            description: text?.trim() || null,
            dataset_id: candidate.datasetId ?? null,
            mapping: candidate.mapping ?? null,
            requirements,
            review: aiReview,
          },
        }),
      ),
    onSuccess: onSaved,
  });

  const f = formulation.data;
  const warnings = issues.filter((i) => i.severity !== "info");

  return (
    <div className="grid items-start gap-6 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {ungrounded.length > 0 && (
          <Alert variant="destructive">
            <TriangleAlert className="size-4" />
            <AlertTitle>
              {ungrounded.length} number(s) were not found in your description
            </AlertTitle>
            <AlertDescription>
              <ul className="mt-1 list-disc pl-4">
                {ungrounded.map((u) => (
                  <li key={u.field}>
                    {u.field} = <span className="font-mono">{fmt(u.value)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2">
                The AI may have invented these. Go back and state them explicitly, or check them
                carefully before approving.
              </p>
            </AlertDescription>
          </Alert>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{f?.title ?? "Model"}</CardTitle>
            <CardDescription>
              This is exactly what will be solved. It is generated from the model by code, not
              written by the AI.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {!f ? (
              <div className="space-y-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : (
              <>
                <section className="space-y-2">
                  <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Objective
                  </h4>
                  <p>{f.objective_english}</p>
                  <div className="rounded-md bg-muted/50 px-4 py-2">
                    <Tex block>{f.objective_latex}</Tex>
                  </div>
                </section>

                <section className="space-y-3">
                  <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Subject to
                  </h4>
                  {f.constraints.map((c) => (
                    <ConstraintCard key={c.name} group={c} />
                  ))}
                  <div className="rounded-md bg-muted/50 px-4 py-2">
                    <Tex block>{f.domain_latex}</Tex>
                  </div>
                </section>

                <section className="space-y-2">
                  <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                    Sets
                  </h4>
                  <dl className="grid gap-2 text-sm">
                    {f.sets.map((s) => (
                      <div key={s.symbol} className="flex min-w-0 gap-3">
                        <dt className="w-40 shrink-0">
                          <Tex>{s.symbol}</Tex>{" "}
                          <span className="text-muted-foreground">
                            {s.name} ({s.members.length})
                          </span>
                        </dt>
                        <dd className="min-w-0 font-mono text-xs leading-5 break-words">
                          {s.members.slice(0, SET_PREVIEW).join(", ")}
                          {s.members.length > SET_PREVIEW && (
                            <span className="text-muted-foreground">
                              {" "}
                              +{s.members.length - SET_PREVIEW} more
                            </span>
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>

                {f.notes.length > 0 && (
                  <section className="space-y-2">
                    {f.notes.map((n) => (
                      <p key={n} className="flex gap-2 text-sm">
                        <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" /> {n}
                      </p>
                    ))}
                  </section>
                )}
              </>
            )}
            {formulation.error && (
              <p className="text-sm text-destructive">{formulation.error.message}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4 lg:sticky lg:top-20">
        <TraceabilityPanel report={traceability.data} loading={traceability.isPending} />
        {traceability.error && (
          <p className="text-sm text-destructive">{traceability.error.message}</p>
        )}
        <AuditPanel report={audit.data} loading={audit.isPending} />
        {audit.error && <p className="text-sm text-destructive">{audit.error.message}</p>}

        {requirements.length > 0 && (
          <RequirementsPanel requirements={requirements} problem={problem} />
        )}

        {warnings.length > 0 && (
          <Alert>
            <TriangleAlert className="size-4" />
            <AlertTitle>Data notes</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {warnings.map((w, i) => (
                  <li key={i}>{w.message}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {trace && trace.calls.length > 0 && (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <Cpu className="size-3.5" />
            {trace.calls.length} AI call(s) · {fmt(
              trace.calls.reduce((s, c) => s + c.latency_ms, 0) / 1000,
            )} s · {trace.calls[0].model}
            {trace.calls.some((c) => !c.ok) && " · self-corrected"}
          </p>
        )}

        {solve.error && (
          <Alert variant="destructive">
            <AlertTitle>Solve failed</AlertTitle>
            <AlertDescription>{solve.error.message}</AlertDescription>
          </Alert>
        )}

        {unsupported && (
          <Alert variant="destructive">
            <TriangleAlert className="size-4" />
            <AlertTitle>Part of your request is not modelled</AlertTitle>
            <AlertDescription>
              The result will ignore it. Rephrase the problem without it, or approve only if it
              truly does not matter.
            </AlertDescription>
          </Alert>
        )}

        <div className="flex gap-2">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft /> Back
          </Button>
          <Button
            className="flex-1"
            variant={blockers ? "destructive" : "default"}
            disabled={!f || solve.isPending || traceability.isPending}
            onClick={() => solve.mutate()}
          >
            {solve.isPending ? <Loader2 className="animate-spin" /> : <Play />}
            {blockers ? `Approve despite ${blockers} open issue(s)` : "Approve & solve"}
          </Button>
        </div>
      </div>
    </div>
  );
}

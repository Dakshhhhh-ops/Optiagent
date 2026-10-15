"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Printer, TriangleAlert, XCircle } from "lucide-react";
import Link from "next/link";

import { Tex } from "@/components/tex";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type Check, client, unwrap } from "@/lib/api";
import { fmt } from "@/lib/format";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 break-inside-avoid">
      <h2 className="border-b pb-1 text-sm font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

function CheckLine({ c }: { c: Check }) {
  const warn = !c.passed && c.severity === "warning";
  const Icon = c.passed ? CheckCircle2 : warn ? TriangleAlert : XCircle;
  return (
    <li className="flex gap-2">
      <Icon className={`mt-0.5 size-4 shrink-0 ${c.passed ? "text-primary" : warn ? "text-amber-600" : "text-destructive"}`} />
      <span>
        {c.name.replaceAll("_", " ")}
        {c.detail && <span className="text-muted-foreground"> — {c.detail}</span>}
      </span>
    </li>
  );
}

export function ProjectReport({ id }: { id: string }) {
  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () =>
      unwrap(client.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })),
  });
  const formulation = useQuery({
    queryKey: ["formulation", project.data?.problem],
    queryFn: () => unwrap(client.POST("/api/v1/formulation", { body: project.data!.problem })),
    enabled: !!project.data,
  });

  if (project.isPending) return <Skeleton className="h-96 w-full" />;
  if (project.error) return <p className="text-sm text-destructive">{project.error.message}</p>;

  const p = project.data;
  const r = p.report;
  const f = formulation.data;
  const s = r.solution;
  const minimize = r.model.sense === "minimize";

  return (
    <article className="space-y-8 text-sm">
      <div className="flex items-center justify-between gap-3 print:hidden">
        <Button variant="outline" size="sm" asChild>
          <Link href={`/projects/${p.id}`}>
            <ArrowLeft /> Back to project
          </Link>
        </Button>
        <Button size="sm" onClick={() => window.print()}>
          <Printer /> Print or save as PDF
        </Button>
      </div>

      <header className="space-y-1">
        <p className="text-xs tracking-wide text-muted-foreground uppercase">OptiAgent report</p>
        <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
        <p className="text-muted-foreground">
          <span className="capitalize">{p.kind}</span> problem · solved {new Date(p.created_at).toLocaleString()} ·{" "}
          {r.verified ? "plan verified optimal against the model and the data" : `no verified plan (${r.outcome.replace("_", " ")})`}
          {p.formulation_status === "needs_review" && " · formulation has unresolved requirements"}
          {p.formulation_status === "unsupported" && " · part of the request is not modelled"}
        </p>
      </header>

      {p.description && (
        <Section title="Problem as described">
          <p className="whitespace-pre-wrap">{p.description}</p>
        </Section>
      )}

      <Section title="Result">
        {s ? (
          <p>
            <span className="text-3xl font-semibold">{fmt(r.result.objective)}</span>{" "}
            <span className="text-muted-foreground">
              {minimize ? "minimum total cost" : "maximum total score"} · solved by {r.result.solver} ·{" "}
              {r.stats.variables} variables, {r.stats.constraints} constraints
            </span>
          </p>
        ) : (
          <p>No feasible plan exists. {r.diagnosis?.explanation}</p>
        )}
      </Section>

      {f && (
        <Section title="Model">
          <p>{f.objective_english}</p>
          <Tex block>{f.objective_latex}</Tex>
          {f.constraints.map((c) => (
            <div key={c.name} className="space-y-1">
              <p className="font-medium">
                {c.name} <span className="font-normal text-muted-foreground">— {c.english}</span>
              </p>
              <Tex block>{c.latex}</Tex>
              <ul className="columns-2 gap-6 text-xs text-muted-foreground">
                {c.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
          <Tex block>{f.domain_latex}</Tex>
          {f.notes.length > 0 && (
            <ul className="list-disc pl-5 text-muted-foreground">
              {f.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {s && (
        <Section title={s.kind === "transportation" ? "Shipment plan" : "Assignment plan"}>
          <table className="w-full">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-1.5 text-left font-medium">{s.kind === "transportation" ? "From" : "Agent"}</th>
                <th className="py-1.5 text-left font-medium">{s.kind === "transportation" ? "To" : "Task"}</th>
                {s.kind === "transportation" && <th className="py-1.5 text-right font-medium">Quantity</th>}
                <th className="py-1.5 text-right font-medium">{s.kind === "transportation" ? "Unit cost" : "Value"}</th>
                {s.kind === "transportation" && <th className="py-1.5 text-right font-medium">Cost</th>}
              </tr>
            </thead>
            <tbody className="divide-y">
              {s.kind === "transportation"
                ? s.shipments.map((x) => (
                    <tr key={`${x.source}-${x.destination}`}>
                      <td className="py-1.5">{x.source}</td>
                      <td className="py-1.5">{x.destination}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{fmt(x.quantity)}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{fmt(x.unit_cost)}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{fmt(x.cost)}</td>
                    </tr>
                  ))
                : s.assignments.map((x) => (
                    <tr key={`${x.agent}-${x.task}`}>
                      <td className="py-1.5">{x.agent}</td>
                      <td className="py-1.5">{x.task}</td>
                      <td className="py-1.5 text-right font-mono tabular-nums">{fmt(x.value)}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </Section>
      )}

      {r.insights.filter((i) => i.kind === "binding" || i.kind === "limit" || i.kind === "unused_option").length > 0 && (
        <Section title="What drives the plan">
          <ul className="list-disc space-y-1 pl-5">
            {r.insights
              .filter((i) => i.kind === "binding" || i.kind === "limit" || i.kind === "unused_option")
              .slice(0, 10)
              .map((i) => (
                <li key={i.source}>{i.text}</li>
              ))}
          </ul>
        </Section>
      )}

      <Section title="Checks">
        <div className="grid gap-6 sm:grid-cols-2 print:grid-cols-2">
          <ul className="space-y-1">
            {r.prechecks.map((c) => (
              <CheckLine key={c.name} c={c} />
            ))}
          </ul>
          <ul className="space-y-1">
            {r.verification.checks.map((c) => (
              <CheckLine key={c.name} c={c} />
            ))}
          </ul>
        </div>
      </Section>

      <footer className="border-t pt-3 text-xs text-muted-foreground">
        Generated by OptiAgent. The model was built and solved deterministically; every number comes
        from the solver or from the problem as approved.
      </footer>
    </article>
  );
}

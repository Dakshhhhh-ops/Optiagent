import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Circle,
  FileSpreadsheet,
  MessageSquareText,
  ShieldCheck,
  Sigma,
  UserCheck,
} from "lucide-react";

import Link from "next/link";

import { AppHeader } from "@/components/app-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const PIPELINE = [
  {
    icon: MessageSquareText,
    title: "Describe",
    body: "Plain-English problem plus clarifying questions for anything missing.",
  },
  {
    icon: FileSpreadsheet,
    title: "Ground in data",
    body: "Upload CSV or Excel. Columns are mapped, values loaded by code — never copied by the LLM.",
  },
  {
    icon: UserCheck,
    title: "Confirm",
    body: "Review the formulation in plain English and math before anything is solved.",
  },
  {
    icon: Sigma,
    title: "Solve",
    body: "Deterministic model builder and OR-Tools solver.",
  },
  {
    icon: ShieldCheck,
    title: "Audit",
    body: "Solution checks plus a formulation audit that targets real LLM modelling errors.",
  },
  {
    icon: BarChart3,
    title: "Explain",
    body: "Shadow prices, sensitivity ranges and what-ifs — every number traced to the solver.",
  },
];

const PHASES = [
  { n: 0, title: "Foundations", done: "docker compose up runs everything; CI green" },
  { n: 1, title: "Solver engine", done: "5 hand-written instances solve correctly" },
  { n: 2, title: "Data ingestion & first UI", done: "Upload → map → solve → flow diagram" },
  { n: 3, title: "LLM extraction & confirmation", done: "20 problems run end to end" },
  { n: 4, title: "Formulation audit", done: "Catches most injected errors" },
  { n: 5, title: "Analysis & explanation", done: "Duals match a manual calculation" },
  { n: 6, title: "Evaluation", done: "Results table and error distribution" },
  { n: 7, title: "Product hardening", done: "A real user runs it on their own data" },
];

const CURRENT_PHASE = 3;

export default function OverviewPage() {
  return (
    <>
      <AppHeader title="Overview" />
      <main className="mx-auto w-full max-w-6xl space-y-10 p-6 md:p-10">
        <section className="space-y-3">
          <Badge variant="secondary">Transportation &amp; assignment · v1</Badge>
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Natural language to <span className="text-primary">verified</span> optimization
          </h2>
          <p className="max-w-2xl text-muted-foreground">
            OptiAgent turns a planning problem and your tabular data into a linear or mixed-integer
            program, solves it, audits the formulation, and explains the result in business
            language. The LLM never produces the final numbers.
          </p>
          <Button asChild className="mt-2">
            <Link href="/problems/new">
              New problem <ArrowRight />
            </Link>
          </Button>
        </section>

        <section className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground">Pipeline</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PIPELINE.map((step, i) => (
              <Card key={step.title}>
                <CardHeader>
                  <div className="mb-2 flex items-center gap-3">
                    <div className="flex size-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <step.icon className="size-4" />
                    </div>
                    <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
                  </div>
                  <CardTitle>{step.title}</CardTitle>
                  <CardDescription>{step.body}</CardDescription>
                </CardHeader>
              </Card>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <h3 className="text-sm font-medium text-muted-foreground">Roadmap</h3>
          <Card>
            <CardContent className="divide-y p-0">
              {PHASES.map((phase) => {
                const complete = phase.n < CURRENT_PHASE;
                const active = phase.n === CURRENT_PHASE;
                return (
                  <div key={phase.n} className="flex items-center gap-4 px-6 py-3">
                    {complete ? (
                      <CheckCircle2 className="size-4 shrink-0 text-primary" />
                    ) : (
                      <Circle
                        className={`size-4 shrink-0 ${active ? "text-primary" : "text-muted-foreground/50"}`}
                      />
                    )}
                    <span className="w-8 font-mono text-xs text-muted-foreground">P{phase.n}</span>
                    <span className="flex-1 text-sm font-medium">{phase.title}</span>
                    <span className="hidden text-sm text-muted-foreground md:block">
                      {phase.done}
                    </span>
                    {active && <Badge>In progress</Badge>}
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </section>
      </main>
    </>
  );
}

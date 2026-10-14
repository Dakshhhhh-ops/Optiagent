"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Info,
  Loader2,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  type AssignmentMapping,
  client,
  type DataIssue,
  type DatasetDetail,
  type Mapping,
  type Problem,
  type ProblemKind,
  type TransportationMapping,
  unwrap,
} from "@/lib/api";
import { fmt } from "@/lib/format";

import {
  defaultKeyValue,
  defaultPairLayout,
  KeyValueEditor,
  PairLayoutEditor,
} from "./mapping-fields";

function fallbackMapping(kind: ProblemKind, dataset: DatasetDetail): Mapping {
  const pair = defaultPairLayout(dataset.tables);
  if (kind === "transportation") {
    const kv = defaultKeyValue(dataset.tables);
    return {
      kind,
      name: "Transportation problem",
      sense: "minimize",
      demand_constraint: "equal",
      costs: pair,
      supply: kv,
      demand: kv,
    };
  }
  return { kind, name: "Assignment problem", sense: "minimize", values: pair };
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function SenseToggle({
  value,
  onChange,
}: {
  value: "minimize" | "maximize";
  onChange: (v: "minimize" | "maximize") => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">Objective</Label>
      <ToggleGroup
        type="single"
        variant="outline"
        value={value}
        onValueChange={(v) => v && onChange(v as "minimize" | "maximize")}
      >
        <ToggleGroupItem value="minimize" className="px-4 text-xs">
          Minimize
        </ToggleGroupItem>
        <ToggleGroupItem value="maximize" className="px-4 text-xs">
          Maximize
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
  );
}

function TransportationForm({
  dataset,
  mapping,
  onChange,
}: {
  dataset: DatasetDetail;
  mapping: TransportationMapping;
  onChange: (m: TransportationMapping) => void;
}) {
  return (
    <>
      <Section title="Costs" description="Cost of shipping one unit on each route.">
        <PairLayoutEditor
          tables={dataset.tables}
          value={mapping.costs}
          onChange={(costs) => onChange({ ...mapping, costs })}
          labels={{
            from: "Source",
            to: "Destination",
            value: "Unit cost",
            capacity: "Route capacity",
          }}
        />
      </Section>
      <Section title="Supply" description="How much each source can ship.">
        <KeyValueEditor
          tables={dataset.tables}
          value={mapping.supply}
          onChange={(supply) => onChange({ ...mapping, supply })}
          idLabel="Source"
          valueLabel="Supply"
        />
      </Section>
      <Section title="Demand" description="How much each destination needs.">
        <KeyValueEditor
          tables={dataset.tables}
          value={mapping.demand}
          onChange={(demand) => onChange({ ...mapping, demand })}
          idLabel="Destination"
          valueLabel="Demand"
        />
      </Section>
      <Section title="Rules" description="How the model treats the numbers.">
        <div className="flex flex-wrap gap-6">
          <SenseToggle value={mapping.sense} onChange={(sense) => onChange({ ...mapping, sense })} />
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Each destination receives</Label>
            <ToggleGroup
              type="single"
              variant="outline"
              value={mapping.demand_constraint}
              onValueChange={(v) =>
                v && onChange({ ...mapping, demand_constraint: v as "equal" | "at_least" })
              }
            >
              <ToggleGroupItem value="equal" className="px-4 text-xs">
                Exactly its demand
              </ToggleGroupItem>
              <ToggleGroupItem value="at_least" className="px-4 text-xs">
                At least its demand
              </ToggleGroupItem>
            </ToggleGroup>
          </div>
        </div>
      </Section>
    </>
  );
}

function AssignmentForm({
  dataset,
  mapping,
  onChange,
}: {
  dataset: DatasetDetail;
  mapping: AssignmentMapping;
  onChange: (m: AssignmentMapping) => void;
}) {
  return (
    <>
      <Section
        title="Values"
        description="Cost or preference for each allowed agent–task pair. Missing pairs are not allowed."
      >
        <PairLayoutEditor
          tables={dataset.tables}
          value={mapping.values}
          onChange={(values) => onChange({ ...mapping, values })}
          labels={{ from: "Agent", to: "Task", value: "Cost or score" }}
        />
      </Section>
      {(
        [
          {
            key: "agent_capacity",
            title: "Agent capacity",
            description: "Maximum tasks per agent. Without a table, each agent takes at most one.",
            idLabel: "Agent",
            valueLabel: "Max tasks",
          },
          {
            key: "task_required",
            title: "Task requirements",
            description: "Agents each task needs. Without a table, each task needs exactly one.",
            idLabel: "Task",
            valueLabel: "Agents needed",
          },
        ] as const
      ).map((s) => {
        const kv = mapping[s.key];
        return (
          <Section key={s.key} title={s.title} description={s.description}>
            <label className="mb-4 flex items-center gap-2 text-sm">
              <Checkbox
                checked={!!kv}
                onCheckedChange={(checked) =>
                  onChange({ ...mapping, [s.key]: checked ? defaultKeyValue(dataset.tables) : null })
                }
              />
              Use a table
            </label>
            {kv && (
              <KeyValueEditor
                tables={dataset.tables}
                value={kv}
                onChange={(next) => onChange({ ...mapping, [s.key]: next })}
                idLabel={s.idLabel}
                valueLabel={s.valueLabel}
              />
            )}
          </Section>
        );
      })}
      <Section title="Rules" description="Minimize total cost, or maximize total preference.">
        <SenseToggle value={mapping.sense} onChange={(sense) => onChange({ ...mapping, sense })} />
      </Section>
    </>
  );
}

const ISSUE_STYLE = {
  error: { icon: AlertCircle, className: "text-destructive" },
  warning: { icon: TriangleAlert, className: "text-amber-600 dark:text-amber-400" },
  info: { icon: Info, className: "text-muted-foreground" },
} as const;

function IssueList({ issues }: { issues: DataIssue[] }) {
  const order = { error: 0, warning: 1, info: 2 };
  const sorted = [...issues].sort((a, b) => order[a.severity] - order[b.severity]);
  return (
    <ul className="space-y-2">
      {sorted.map((issue, i) => {
        const { icon: Icon, className } = ISSUE_STYLE[issue.severity];
        const where = [issue.table, issue.row && `row ${issue.row}`, issue.column]
          .filter(Boolean)
          .join(" · ");
        return (
          <li key={i} className="flex gap-2 text-sm">
            <Icon className={`mt-0.5 size-4 shrink-0 ${className}`} />
            <div className="min-w-0">
              <p>{issue.message}</p>
              {where && <p className="font-mono text-xs text-muted-foreground">{where}</p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ProblemSummary({ problem }: { problem: Problem }) {
  const rows =
    problem.kind === "transportation"
      ? [
          ["Sources", problem.sources.length],
          ["Destinations", problem.destinations.length],
          ["Allowed routes", problem.routes.length],
          ["Total supply", problem.sources.reduce((s, x) => s + x.supply, 0)],
          ["Total demand", problem.destinations.reduce((s, x) => s + x.demand, 0)],
        ]
      : [
          ["Agents", problem.agents.length],
          ["Tasks", problem.tasks.length],
          ["Allowed pairs", problem.pairings.length],
          ["Agent slots", problem.agents.reduce((s, a) => s + (a.capacity ?? 1), 0)],
          ["Positions to fill", problem.tasks.reduce((s, t) => s + (t.required ?? 1), 0)],
        ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="text-right font-mono tabular-nums">{fmt(value as number)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function MappingStep({
  kind,
  dataset,
  mapping,
  onMappingChange,
  onBack,
  onReview,
}: {
  kind: ProblemKind;
  dataset: DatasetDetail;
  mapping: Mapping | null;
  onMappingChange: (m: Mapping) => void;
  onBack: () => void;
  onReview: (problem: Problem, issues: DataIssue[]) => void;
}) {
  const suggestion = useQuery({
    queryKey: ["suggest", dataset.meta.id, kind],
    queryFn: () =>
      unwrap(
        client.POST("/api/v1/datasets/{dataset_id}/suggest", {
          params: { path: { dataset_id: dataset.meta.id } },
          body: { kind },
        }),
      ),
    enabled: mapping === null,
  });

  const suggested = suggestion.data?.mapping?.kind === kind ? suggestion.data.mapping : null;
  const effective: Mapping | null =
    mapping ?? (suggestion.isPending ? null : (suggested ?? fallbackMapping(kind, dataset)));

  const build = useQuery({
    queryKey: ["build", dataset.meta.id, effective],
    queryFn: () =>
      unwrap(
        client.POST("/api/v1/datasets/{dataset_id}/build", {
          params: { path: { dataset_id: dataset.meta.id } },
          body: effective!,
        }),
      ),
    enabled: effective !== null,
    placeholderData: keepPreviousData,
  });

  if (!effective) {
    return (
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const problem = build.data?.problem ?? null;
  const issues = build.data?.issues ?? [];
  const errors = issues.filter((i) => i.severity === "error").length;

  return (
    <div className="grid items-start gap-6 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {mapping === null && suggestion.data && (
          <Alert>
            <Sparkles className="size-4" />
            <AlertTitle>
              {suggested ? "Mapping suggested from your data" : "Could not suggest a full mapping"}
            </AlertTitle>
            <AlertDescription>
              {suggestion.data.notes.join(" · ")}. Check each field before solving.
            </AlertDescription>
          </Alert>
        )}
        {effective.kind === "transportation" ? (
          <TransportationForm dataset={dataset} mapping={effective} onChange={onMappingChange} />
        ) : (
          <AssignmentForm dataset={dataset} mapping={effective} onChange={onMappingChange} />
        )}
      </div>

      <div className="space-y-4 lg:sticky lg:top-20">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              {build.isFetching ? (
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              ) : problem ? (
                <CheckCircle2 className="size-4 text-primary" />
              ) : (
                <AlertCircle className="size-4 text-destructive" />
              )}
              {problem ? "Data is valid" : errors ? `${errors} error(s) to fix` : "Validating…"}
            </CardTitle>
            <CardDescription>
              Values are read from your files by code. Nothing is typed in by the AI.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {problem && <ProblemSummary problem={problem} />}
            {build.error && <p className="text-sm text-destructive">{build.error.message}</p>}
            {issues.length > 0 && <IssueList issues={issues} />}
          </CardContent>
        </Card>

        <div className="flex gap-2">
          <Button variant="outline" onClick={onBack}>
            <ArrowLeft /> Data
          </Button>
          <Button
            className="flex-1"
            disabled={!problem || build.isFetching}
            onClick={() => problem && onReview(problem, issues)}
          >
            Review model <ArrowRight />
          </Button>
        </div>
      </div>
    </div>
  );
}

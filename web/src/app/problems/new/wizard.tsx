"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import type { DatasetDetail, Mapping, ProblemKind, SolveReport } from "@/lib/api";
import { cn } from "@/lib/utils";

import { DataStep } from "./data-step";
import { MappingStep } from "./mapping-step";
import { ResultsStep } from "./results-step";

type Step = "data" | "map" | "results";

const STEPS: { id: Step; label: string }[] = [
  { id: "data", label: "Data" },
  { id: "map", label: "Map & validate" },
  { id: "results", label: "Results" },
];

function Stepper({ current }: { current: Step }) {
  const index = STEPS.findIndex((s) => s.id === current);
  return (
    <ol className="flex items-center gap-2 text-sm">
      {STEPS.map((s, i) => (
        <li key={s.id} className="flex items-center gap-2">
          <span
            className={cn(
              "flex size-6 items-center justify-center rounded-full border text-xs font-medium",
              i < index && "border-primary bg-primary text-primary-foreground",
              i === index && "border-primary text-primary",
              i > index && "text-muted-foreground",
            )}
          >
            {i < index ? <Check className="size-3.5" /> : i + 1}
          </span>
          <span className={cn(i === index ? "font-medium" : "text-muted-foreground")}>
            {s.label}
          </span>
          {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-border sm:w-10" />}
        </li>
      ))}
    </ol>
  );
}

export function Wizard() {
  const [step, setStep] = useState<Step>("data");
  const [kind, setKind] = useState<ProblemKind>("transportation");
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [report, setReport] = useState<SolveReport | null>(null);

  return (
    <div className="space-y-8">
      <Stepper current={step} />

      {step === "data" && (
        <DataStep
          kind={kind}
          onKindChange={(k) => {
            setKind(k);
            setMapping(null);
          }}
          dataset={dataset}
          onDataset={(d) => {
            setDataset(d);
            setMapping(null);
          }}
          onNext={() => setStep("map")}
        />
      )}

      {step === "map" && dataset && (
        <MappingStep
          kind={kind}
          dataset={dataset}
          mapping={mapping}
          onMappingChange={setMapping}
          onBack={() => setStep("data")}
          onSolved={(r) => {
            setReport(r);
            setStep("results");
          }}
        />
      )}

      {step === "results" && report && (
        <ResultsStep report={report} onBack={() => setStep("map")} />
      )}
    </div>
  );
}

"use client";

import { useMutation } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useState } from "react";

import {
  type Analysis,
  client,
  type DatasetDetail,
  type Mapping,
  type ProblemKind,
  type SolveReport,
  unwrap,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { AiPanel } from "./ai-panel";
import { type Candidate, ConfirmStep } from "./confirm-step";
import { DataStep } from "./data-step";
import { MappingStep } from "./mapping-step";
import { ResultsStep } from "./results-step";

type Step = "input" | "map" | "confirm" | "results";

const STEPS: { id: Step; label: string }[] = [
  { id: "input", label: "Describe & data" },
  { id: "map", label: "Model" },
  { id: "confirm", label: "Confirm" },
  { id: "results", label: "Results" },
];

function Stepper({ current }: { current: Step }) {
  const index = STEPS.findIndex((s) => s.id === current);
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm">
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
  const [step, setStep] = useState<Step>("input");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<ProblemKind>("transportation");
  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [report, setReport] = useState<SolveReport | null>(null);

  const analyze = useMutation({
    mutationFn: () =>
      unwrap(
        client.POST("/api/v1/agent/analyze", {
          body: { text, dataset_id: dataset?.meta.id ?? null },
        }),
      ),
    onSuccess: ({ analysis: a }) => {
      setAnalysis(a);
      setAnswers({});
      if (a.kind !== "unsupported") setKind(a.kind);
    },
  });

  function review(c: Candidate) {
    setCandidate(c);
    setStep("confirm");
  }

  return (
    <div className="space-y-8">
      <Stepper current={step} />

      {step === "input" && (
        <DataStep
          text={text}
          onTextChange={(t) => {
            setText(t);
            setAnalysis(null);
          }}
          kind={kind}
          onKindChange={(k) => {
            setKind(k);
            setMapping(null);
          }}
          dataset={dataset}
          onDataset={(d) => {
            setDataset(d);
            setMapping(null);
            setAnalysis(null);
          }}
          onAnalyze={() => analyze.mutate()}
          analyzing={analyze.isPending}
          analyzeError={analyze.error}
          aiPanel={
            analysis && (
              <AiPanel
                text={text}
                datasetId={dataset?.meta.id ?? null}
                analysis={analysis}
                kind={kind}
                onKindChange={setKind}
                answers={answers}
                onAnswersChange={setAnswers}
                onCandidate={review}
              />
            )
          }
          onManual={() => setStep("map")}
        />
      )}

      {step === "map" && dataset && (
        <MappingStep
          kind={kind}
          dataset={dataset}
          mapping={mapping}
          onMappingChange={setMapping}
          onBack={() => setStep("input")}
          onReview={(problem, issues) =>
            review({
              problem,
              source: "manual",
              issues,
              requirements: analysis?.requirements,
            })
          }
        />
      )}

      {step === "confirm" && candidate && (
        <ConfirmStep
          candidate={candidate}
          onBack={() => setStep(candidate.source === "manual" ? "map" : "input")}
          onSolved={(r) => {
            setReport(r);
            setStep("results");
          }}
        />
      )}

      {step === "results" && report && (
        <ResultsStep report={report} onBack={() => setStep("confirm")} />
      )}
    </div>
  );
}

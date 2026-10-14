"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Columns3, FileSpreadsheet, Loader2, Network, Sparkles, Upload, Users } from "lucide-react";
import { useRef, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { client, type DatasetDetail, type ProblemKind, unwrap } from "@/lib/api";
import { cn } from "@/lib/utils";

import { TablePreview } from "./table-preview";

const KINDS: { value: ProblemKind; title: string; body: string; icon: typeof Network }[] = [
  {
    value: "transportation",
    title: "Transportation",
    body: "Ship goods from sources to destinations at minimum total cost.",
    icon: Network,
  },
  {
    value: "assignment",
    title: "Assignment",
    body: "Match people or machines to tasks by cost or preference.",
    icon: Users,
  },
];

const ACCEPT = ".csv,.tsv,.xlsx";

const EXAMPLES = [
  {
    label: "Factories → cities",
    text: "The factory in Plant C can send up to 40 tons, shipping to Austin at $3 per ton and Seattle at $8 per ton. The factory in Plant B can send up to 30 tons, shipping to Austin at $11 per ton, Seattle at $18 per ton and Denver at $19 per ton. Austin requires 20 tons, Seattle 20 tons and Denver 30 tons. Plant C cannot ship to Denver. Find the shipping plan with the lowest total cost.",
  },
  {
    label: "TAs → lab sections",
    text: "Four TAs rank lab sections from 1 to 10. Ravi: L1 8, L2 2, L3 8. Omar: L1 8, L2 10, L3 4. Lena: L1 5, L2 8, L3 9. Meera: L1 4, L2 7, L3 5. L2 needs two TAs; L1 and L3 need one each. Each TA takes at most one section. Maximize the total preference score.",
  },
  {
    label: "With uploaded data",
    text: "Ship grain from our silos to the mills at the lowest total cost. Every mill must get exactly what it needs. The numbers are in the uploaded files.",
  },
];

export function DataStep({
  text,
  onTextChange,
  kind,
  onKindChange,
  dataset,
  onDataset,
  onAnalyze,
  analyzing,
  analyzeError,
  aiPanel,
  onManual,
}: {
  text: string;
  onTextChange: (text: string) => void;
  kind: ProblemKind;
  onKindChange: (kind: ProblemKind) => void;
  dataset: DatasetDetail | null;
  onDataset: (dataset: DatasetDetail) => void;
  onAnalyze: () => void;
  analyzing: boolean;
  analyzeError: Error | null;
  aiPanel: React.ReactNode;
  onManual: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const system = useQuery({
    queryKey: ["system-status"],
    queryFn: () => unwrap(client.GET("/api/v1/system/status")),
    staleTime: 30_000,
  });
  const ollama = system.data?.ollama;
  const aiProblem = system.error
    ? "the API is not reachable"
    : ollama && !ollama.reachable
      ? `Ollama is not running at ${ollama.base_url}`
      : ollama && !ollama.configured_model_available
        ? `the model ${ollama.configured_model} is not downloaded (run: ollama pull ${ollama.configured_model})`
        : null;

  const samples = useQuery({
    queryKey: ["samples"],
    queryFn: () => unwrap(client.GET("/api/v1/datasets/samples")),
  });

  const upload = useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return unwrap(
        client.POST("/api/v1/datasets", {
          body: { files: [] },
          bodySerializer: () => form,
        }),
      );
    },
    onSuccess: onDataset,
  });

  const fromSample = useMutation({
    mutationFn: (sampleId: string) =>
      unwrap(
        client.POST("/api/v1/datasets/samples/{sample_id}", {
          params: { path: { sample_id: sampleId } },
        }),
      ),
    onSuccess: onDataset,
  });

  const busy = upload.isPending || fromSample.isPending;
  const error = upload.error ?? fromSample.error;

  function handleFiles(list: FileList | null) {
    const files = Array.from(list ?? []);
    if (files.length) upload.mutate(files);
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h3 className="text-sm font-medium">1. Describe the problem</h3>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((e) => (
              <Button
                key={e.label}
                variant="outline"
                size="sm"
                className="h-7 text-xs"
                onClick={() => onTextChange(e.text)}
              >
                {e.label}
              </Button>
            ))}
          </div>
        </div>
        <Textarea
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          placeholder="For example: Three warehouses supply five stores. Mumbai can ship 400 units… Minimize total shipping cost."
          className="min-h-32"
        />
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-medium">
          2. Problem type{" "}
          <span className="font-normal text-muted-foreground">
            (detected for you when you analyze with AI)
          </span>
        </h3>
        <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Problem type">
          {KINDS.map((k) => (
            <button
              key={k.value}
              type="button"
              role="radio"
              aria-checked={kind === k.value}
              onClick={() => onKindChange(k.value)}
              className={cn(
                "flex items-start gap-3 rounded-xl border p-4 text-left transition-colors hover:bg-muted/50",
                kind === k.value && "border-primary bg-primary/5 ring-1 ring-primary",
              )}
            >
              <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                <k.icon className="size-4" />
              </div>
              <div className="space-y-1">
                <p className="font-medium">{k.title}</p>
                <p className="text-sm text-muted-foreground">{k.body}</p>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-medium">
          3. Add data{" "}
          <span className="font-normal text-muted-foreground">
            (optional if the description has all the numbers)
          </span>
        </h3>
        <div className="grid gap-4 lg:grid-cols-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              handleFiles(e.dataTransfer.files);
            }}
            className={cn(
              "flex min-h-48 flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-6 text-center transition-colors lg:col-span-3",
              dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25",
            )}
          >
            {upload.isPending ? (
              <Loader2 className="size-8 animate-spin text-muted-foreground" />
            ) : (
              <Upload className="size-8 text-muted-foreground" />
            )}
            <div className="space-y-1">
              <p className="font-medium">Drop CSV or Excel files here</p>
              <p className="text-sm text-muted-foreground">
                For example costs.csv, supply.csv and demand.csv. Every sheet of an .xlsx becomes a
                table.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => inputRef.current?.click()}
            >
              Choose files
            </Button>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                handleFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Or start from a sample</CardTitle>
              <CardDescription>Hand-verified datasets with known answers.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {samples.isPending &&
                [0, 1, 2].map((i) => <Skeleton key={i} className="h-14 w-full" />)}
              {samples.data?.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    onKindChange(s.kind as ProblemKind);
                    fromSample.mutate(s.id);
                  }}
                  className="flex w-full items-start gap-3 rounded-lg border p-3 text-left text-sm transition-colors hover:bg-muted/50 disabled:opacity-50"
                >
                  <FileSpreadsheet className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{s.name}</span>
                      <Badge variant="secondary" className="shrink-0 capitalize">
                        {s.kind}
                      </Badge>
                    </div>
                    <p className="line-clamp-2 text-xs text-muted-foreground">{s.description}</p>
                  </div>
                </button>
              ))}
              {samples.error && (
                <p className="text-sm text-destructive">{samples.error.message}</p>
              )}
            </CardContent>
          </Card>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTitle>Could not load the data</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}
      </section>

      {dataset && (
        <section className="space-y-3">
          <h3 className="text-sm font-medium">
            Your tables{" "}
            <span className="font-normal text-muted-foreground">
              ({dataset.tables.length} found)
            </span>
          </h3>
          <TablePreview tables={dataset.tables} />
        </section>
      )}

      {aiProblem && (
        <Alert>
          <AlertTitle>AI analysis is unavailable</AlertTitle>
          <AlertDescription>
            Because {aiProblem}. You can still upload data and map the columns manually.
          </AlertDescription>
        </Alert>
      )}

      {analyzeError && (
        <Alert variant="destructive">
          <AlertTitle>Analysis failed</AlertTitle>
          <AlertDescription>{analyzeError.message}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-6">
        {!text.trim() && !dataset && (
          <span className="text-sm text-muted-foreground">
            Describe the problem, add data, or both.
          </span>
        )}
        <Button variant="outline" disabled={!dataset} onClick={onManual}>
          <Columns3 /> Map columns manually
        </Button>
        <Button disabled={!text.trim() || analyzing} onClick={onAnalyze}>
          {analyzing ? <Loader2 className="animate-spin" /> : <Sparkles />}
          {analyzing ? "Analyzing…" : "Analyze with AI"}
        </Button>
      </div>

      {aiPanel}
    </div>
  );
}

"use client";

import { useMutation } from "@tanstack/react-query";
import { Ban, Loader2, MessageCircleQuestion, Sparkles, Wand2 } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type Analysis, client, type ProblemKind, unwrap } from "@/lib/api";

import type { Candidate } from "./confirm-step";

export function AiPanel({
  text,
  datasetId,
  analysis,
  kind,
  onKindChange,
  answers,
  onAnswersChange,
  onCandidate,
}: {
  text: string;
  datasetId: string | null;
  analysis: Analysis;
  kind: ProblemKind;
  onKindChange: (k: ProblemKind) => void;
  answers: Record<string, string>;
  onAnswersChange: (a: Record<string, string>) => void;
  onCandidate: (c: Candidate) => void;
}) {
  const extract = useMutation({
    mutationFn: () =>
      unwrap(
        client.POST("/api/v1/agent/extract", {
          body: {
            text,
            kind,
            dataset_id: datasetId,
            answers: analysis.questions
              .filter((q) => answers[q]?.trim())
              .map((q) => ({ question: q, answer: answers[q].trim() })),
          },
        }),
      ),
    onSuccess: (r) => {
      if (r.problem) {
        onCandidate({
          problem: r.problem,
          source: "ai",
          requirements: analysis.requirements,
          ungrounded: r.ungrounded,
          issues: r.issues,
          mapping: r.mapping,
          trace: r.trace,
        });
      }
    },
  });

  if (analysis.kind === "unsupported") {
    return (
      <Alert>
        <Ban className="size-4" />
        <AlertTitle>This problem is outside what OptiAgent supports today</AlertTitle>
        <AlertDescription>
          {analysis.summary} OptiAgent v1 handles transportation and assignment problems only.
        </AlertDescription>
      </Alert>
    );
  }

  const unanswered = analysis.questions.filter((q) => !answers[q]?.trim()).length;
  const failed = extract.data && !extract.data.problem;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4 text-primary" /> What we understood
        </CardTitle>
        <CardDescription>{analysis.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Problem type</Label>
          <ToggleGroup
            type="single"
            variant="outline"
            value={kind}
            onValueChange={(v) => v && onKindChange(v as ProblemKind)}
          >
            <ToggleGroupItem value="transportation" className="px-4 text-xs">
              Transportation
            </ToggleGroupItem>
            <ToggleGroupItem value="assignment" className="px-4 text-xs">
              Assignment
            </ToggleGroupItem>
          </ToggleGroup>
        </div>

        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">
            Requirements found in your description
          </Label>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {analysis.requirements.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ol>
        </div>

        {analysis.questions.length > 0 && (
          <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
            <p className="flex items-center gap-2 text-sm font-medium">
              <MessageCircleQuestion className="size-4 text-primary" />
              Some information seems to be missing
            </p>
            {analysis.questions.map((q) => (
              <div key={q} className="space-y-1.5">
                <Label htmlFor={q} className="text-sm font-normal">
                  {q}
                </Label>
                <Input
                  id={q}
                  value={answers[q] ?? ""}
                  onChange={(e) => onAnswersChange({ ...answers, [q]: e.target.value })}
                  placeholder="Your answer"
                />
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              Leave a question blank if it does not apply.
            </p>
          </div>
        )}

        {extract.error && (
          <Alert variant="destructive">
            <AlertTitle>Could not build the model</AlertTitle>
            <AlertDescription>{extract.error.message}</AlertDescription>
          </Alert>
        )}
        {failed && (
          <Alert variant="destructive">
            <AlertTitle>The data did not load with the proposed mapping</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-4">
                {extract.data?.issues
                  .filter((i) => i.severity === "error")
                  .map((i, n) => (
                    <li key={n}>{i.message}</li>
                  ))}
              </ul>
              Try mapping the columns manually instead.
            </AlertDescription>
          </Alert>
        )}

        <div className="flex items-center justify-end gap-3">
          {unanswered > 0 && (
            <span className="text-xs text-muted-foreground">
              {unanswered} question(s) unanswered
            </span>
          )}
          <Button onClick={() => extract.mutate()} disabled={extract.isPending}>
            {extract.isPending ? <Loader2 className="animate-spin" /> : <Wand2 />}
            {extract.isPending ? "Building model…" : "Build model"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

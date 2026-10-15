"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, FileText, Pencil, Printer, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { client, unwrap } from "@/lib/api";
import { download, planCsv, slug } from "@/lib/export";

import { ResultsStep } from "../../problems/new/results-step";

export function ProjectView({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");

  const project = useQuery({
    queryKey: ["project", id],
    queryFn: () =>
      unwrap(client.GET("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })),
  });

  const rename = useMutation({
    mutationFn: (newName: string) =>
      unwrap(
        client.PATCH("/api/v1/projects/{project_id}", {
          params: { path: { project_id: id } },
          body: { name: newName },
        }),
      ),
    onSuccess: (p) => {
      queryClient.setQueryData(["project", id], p);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setEditing(false);
    },
  });

  if (project.isPending) return <Skeleton className="h-64 w-full" />;
  if (project.error) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-destructive">{project.error.message}</p>
        <Button asChild variant="outline" size="sm">
          <Link href="/projects">All projects</Link>
        </Button>
      </div>
    );
  }

  const p = project.data;
  const csv = planCsv(p.report);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        {editing ? (
          <form
            className="flex max-w-xl items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) rename.mutate(name.trim());
            }}
          >
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus aria-label="Project name" />
            <Button type="submit" size="icon" aria-label="Save name" disabled={rename.isPending}>
              <Check />
            </Button>
            <Button type="button" size="icon" variant="ghost" aria-label="Cancel" onClick={() => setEditing(false)}>
              <X />
            </Button>
          </form>
        ) : (
          <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            {p.name}
            <Button
              variant="ghost"
              size="icon"
              aria-label="Rename project"
              className="print:hidden"
              onClick={() => {
                setName(p.name);
                setEditing(true);
              }}
            >
              <Pencil className="size-4" />
            </Button>
          </h2>
        )}
        <p className="text-sm text-muted-foreground">
          <span className="capitalize">{p.kind}</span> · {p.source === "ai" ? "built from your description" : "built from your data"} ·
          saved {new Date(p.created_at).toLocaleString()}
        </p>
        {p.description && (
          <details className="max-w-3xl text-sm">
            <summary className="cursor-pointer text-muted-foreground">Original description</summary>
            <p className="mt-2 whitespace-pre-wrap rounded-md bg-muted/50 p-3">{p.description}</p>
          </details>
        )}
      </div>

      <ResultsStep
        report={p.report}
        problem={p.problem}
        traceability={p.traceability}
        backLabel="Projects"
        onBack={() => router.push("/projects")}
        actions={
          <div className="flex flex-wrap gap-2 print:hidden">
            {csv && (
              <Button variant="outline" size="sm" onClick={() => download(`${slug(p.name)}.csv`, csv)}>
                <Download /> CSV
              </Button>
            )}
            <Button variant="outline" size="sm" asChild>
              <Link href={`/projects/${p.id}/report`}>
                <FileText /> Report
              </Link>
            </Button>
            <Button variant="outline" size="sm" onClick={() => window.print()}>
              <Printer /> Print
            </Button>
          </div>
        }
      />
    </div>
  );
}

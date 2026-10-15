"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FolderOpen,
  Network,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  Users,
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { client, unwrap } from "@/lib/api";
import { fmt } from "@/lib/format";

export function ProjectList() {
  const queryClient = useQueryClient();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => unwrap(client.GET("/api/v1/projects")),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(client.DELETE("/api/v1/projects/{project_id}", { params: { path: { project_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">Projects</h2>
          <p className="text-muted-foreground">Every problem you approve and solve is saved here.</p>
        </div>
        <Button asChild>
          <Link href="/problems/new">
            <Plus /> New problem
          </Link>
        </Button>
      </div>

      {projects.isPending && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      )}
      {projects.error && <p className="text-sm text-destructive">{projects.error.message}</p>}

      {projects.data?.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <FolderOpen className="size-8 text-muted-foreground" />
            <p className="font-medium">No projects yet</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Describe a problem or upload your data, confirm the model, and solve. The result is
              saved here automatically.
            </p>
            <Button asChild variant="outline" size="sm">
              <Link href="/problems/new">Start a problem</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {projects.data && projects.data.length > 0 && (
        <ul className="space-y-3">
          {projects.data.map((p) => {
            const Icon = p.kind === "transportation" ? Network : Users;
            return (
              <li key={p.id}>
                <Card className="py-4 transition-colors hover:bg-muted/30">
                  <CardContent className="flex items-center gap-4 px-4">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <Icon className="size-5" />
                    </div>
                    <Link href={`/projects/${p.id}`} className="min-w-0 flex-1 space-y-1">
                      <p className="truncate font-medium">{p.name}</p>
                      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        <span className="capitalize">{p.kind}</span>
                        <span>{p.source === "ai" ? "From description" : "From data"}</span>
                        <span>{new Date(p.updated_at).toLocaleString()}</span>
                      </p>
                    </Link>
                    <div className="hidden text-right sm:block">
                      <p className="font-mono text-lg tabular-nums">{fmt(p.objective)}</p>
                      <p className="text-xs text-muted-foreground">{p.status}</p>
                    </div>
                    {p.verified ? (
                      <Badge className="gap-1" title="Proven optimal and re-checked against the data">
                        <ShieldCheck className="size-3.5" /> Plan verified
                      </Badge>
                    ) : (
                      <Badge variant="destructive" className="gap-1">
                        <ShieldAlert className="size-3.5" /> {p.status === "infeasible" ? "Infeasible" : "Not verified"}
                      </Badge>
                    )}
                    {p.formulation_status && p.formulation_status !== "checked" && (
                      <Badge
                        variant={p.formulation_status === "unsupported" ? "destructive" : "secondary"}
                        className="gap-1"
                        title="Whether the model matches the description"
                      >
                        <TriangleAlert className="size-3.5" />
                        {p.formulation_status === "unsupported" ? "Unsupported" : "Needs review"}
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${p.name}`}
                      disabled={remove.isPending}
                      onClick={() => {
                        if (window.confirm(`Delete "${p.name}"? This cannot be undone.`)) remove.mutate(p.id);
                      }}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

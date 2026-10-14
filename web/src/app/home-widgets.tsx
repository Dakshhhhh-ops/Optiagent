"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FolderOpen, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { client, unwrap } from "@/lib/api";
import { fmt } from "@/lib/format";

export function RecentProjects() {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => unwrap(client.GET("/api/v1/projects")),
  });
  const recent = projects.data?.slice(0, 4) ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recent projects</CardTitle>
        <CardDescription>Every approved solve is saved.</CardDescription>
        <CardAction>
          <Link href="/projects" className="flex items-center gap-1 text-sm text-primary hover:underline">
            All <ArrowRight className="size-3.5" />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        {projects.isPending && <Skeleton className="h-24 w-full" />}
        {projects.error && <p className="text-sm text-muted-foreground">Start the API to see your projects.</p>}
        {projects.data && recent.length === 0 && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <FolderOpen className="size-4" /> No projects yet.
          </p>
        )}
        <ul className="divide-y">
          {recent.map((p) => (
            <li key={p.id}>
              <Link href={`/projects/${p.id}`} className="flex items-center gap-3 py-2.5 hover:text-primary">
                {p.verified ? (
                  <ShieldCheck className="size-4 shrink-0 text-primary" aria-label="verified" />
                ) : (
                  <ShieldAlert className="size-4 shrink-0 text-destructive" aria-label="not verified" />
                )}
                <span className="min-w-0 flex-1 truncate text-sm">{p.name}</span>
                <span className="font-mono text-sm tabular-nums">{fmt(p.objective)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function BenchmarkHeadline() {
  const summary = useQuery({
    queryKey: ["benchmarks"],
    queryFn: () => unwrap(client.GET("/api/v1/benchmarks")),
    retry: false,
  });
  const modes = summary.data?.modes ?? [];
  const direct = modes.find((m) => m.mode === "direct");
  const full = modes.find((m) => m.mode === "full" && m.model === direct?.model) ?? modes.find((m) => m.mode === "full");
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Why verification matters</CardTitle>
        <CardDescription>Wrong answers with no warning, on our benchmark.</CardDescription>
        <CardAction>
          <Link href="/benchmarks" className="flex items-center gap-1 text-sm text-primary hover:underline">
            Details <ArrowRight className="size-3.5" />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        {summary.isPending && <Skeleton className="h-24 w-full" />}
        {direct && full ? (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-3xl font-semibold tracking-tight text-destructive">
                {Math.round(direct.silent_error_rate * 100)}%
              </p>
              <p className="text-xs text-muted-foreground">LLM answering directly ({direct.model})</p>
            </div>
            <div>
              <p className="text-3xl font-semibold tracking-tight text-primary">
                {Math.round(full.silent_error_rate * 100)}%
              </p>
              <p className="text-xs text-muted-foreground">OptiAgent, verified ({full.model})</p>
            </div>
          </div>
        ) : (
          !summary.isPending && <p className="text-sm text-muted-foreground">No benchmark results yet.</p>
        )}
      </CardContent>
    </Card>
  );
}

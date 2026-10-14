"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Database, RefreshCw, Server, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { API_URL, client, unwrap } from "@/lib/api";

function StatusBadge({ ok, warn }: { ok: boolean; warn?: boolean }) {
  if (!ok) return <Badge variant="destructive">Unreachable</Badge>;
  if (warn) return <Badge variant="outline">Degraded</Badge>;
  return <Badge>Healthy</Badge>;
}

const SERVICE_ICONS: Record<string, typeof Database> = { postgres: Database, redis: Zap };

export function StatusPanel() {
  const { data, error, isPending, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => unwrap(client.GET("/api/v1/system/status")),
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {dataUpdatedAt ? `Updated ${new Date(dataUpdatedAt).toLocaleTimeString()}` : " "}
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={isFetching ? "animate-spin" : ""} /> Refresh
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div className="space-y-1.5">
              <CardTitle className="flex items-center gap-2">
                <Server className="size-4" /> API
              </CardTitle>
              <CardDescription className="font-mono text-xs">{API_URL}</CardDescription>
            </div>
            {isPending ? <Skeleton className="h-5 w-16" /> : <StatusBadge ok={!error} />}
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {error ? (
              <span>
                Could not reach the API. Start it with{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  uv run uvicorn optiagent_api.main:app --reload
                </code>
              </span>
            ) : (
              <span>Version {data?.version ?? "…"}</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div className="space-y-1.5">
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-4" /> Ollama
              </CardTitle>
              <CardDescription className="font-mono text-xs">
                {data?.ollama.base_url ?? "—"}
              </CardDescription>
            </div>
            {isPending ? (
              <Skeleton className="h-5 w-16" />
            ) : (
              <StatusBadge
                ok={!!data?.ollama.reachable}
                warn={!data?.ollama.configured_model_available}
              />
            )}
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {data?.ollama.reachable ? (
              <>
                <p>
                  Model <span className="font-mono">{data.ollama.configured_model}</span>{" "}
                  {data.ollama.configured_model_available ? (
                    <span className="text-muted-foreground">is available.</span>
                  ) : (
                    <span className="text-destructive">
                      is not pulled. Run{" "}
                      <code className="font-mono">ollama pull {data.ollama.configured_model}</code>
                    </span>
                  )}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {data.ollama.models.map((m) => (
                    <Badge key={m} variant="secondary" className="font-mono">
                      {m}
                    </Badge>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-muted-foreground">
                {data?.ollama.error ?? "Waiting for the API…"}
              </p>
            )}
          </CardContent>
        </Card>

        {data?.services.map((service) => {
          const Icon = SERVICE_ICONS[service.name] ?? Server;
          return (
            <Card key={service.name}>
              <CardHeader className="flex-row items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <CardTitle className="flex items-center gap-2 capitalize">
                    <Icon className="size-4" /> {service.name}
                  </CardTitle>
                  <CardDescription className="font-mono text-xs">{service.detail}</CardDescription>
                </div>
                <StatusBadge ok={service.reachable} />
              </CardHeader>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

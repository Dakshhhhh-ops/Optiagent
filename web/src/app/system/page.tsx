import type { Metadata } from "next";

import { AppHeader } from "@/components/app-header";

import { StatusPanel } from "./status-panel";

export const metadata: Metadata = { title: "System status" };

export default function SystemPage() {
  return (
    <>
      <AppHeader title="System status" />
      <main className="mx-auto w-full max-w-6xl space-y-6 p-6 md:p-10">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">System status</h2>
          <p className="text-muted-foreground">
            Live health of the API, the local LLM and backing services.
          </p>
        </div>
        <StatusPanel />
      </main>
    </>
  );
}

import type { Metadata } from "next";

import { AppHeader } from "@/components/app-header";

import { BenchmarksView } from "./benchmarks-view";

export const metadata: Metadata = { title: "Benchmarks" };

export default function BenchmarksPage() {
  return (
    <>
      <AppHeader title="Benchmarks" />
      <main className="mx-auto w-full max-w-6xl space-y-6 p-6 md:p-10">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">Benchmarks</h2>
          <p className="text-muted-foreground">
            How often each approach ends with a wrong answer the user is never warned about, and
            how well the formulation audit catches modelling errors.
          </p>
        </div>
        <BenchmarksView />
      </main>
    </>
  );
}

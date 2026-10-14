import type { Metadata } from "next";

import { AppHeader } from "@/components/app-header";

import { Wizard } from "./wizard";

export const metadata: Metadata = { title: "New problem" };

export default function NewProblemPage() {
  return (
    <>
      <AppHeader title="New problem" />
      <main className="mx-auto w-full max-w-6xl space-y-6 p-6 md:p-10">
        <div className="space-y-1">
          <h2 className="text-2xl font-semibold tracking-tight">New problem</h2>
          <p className="text-muted-foreground">
            Describe the problem, add your data, confirm the model, then solve.
          </p>
        </div>
        <Wizard />
      </main>
    </>
  );
}

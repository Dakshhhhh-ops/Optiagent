import type { Metadata } from "next";
import { Suspense } from "react";

import { AppHeader } from "@/components/app-header";
import { Skeleton } from "@/components/ui/skeleton";

import { ProjectView } from "./project-view";

export const metadata: Metadata = { title: "Project" };

export default function ProjectPage({ params }: PageProps<"/projects/[id]">) {
  return (
    <>
      <AppHeader title="Project" />
      <main className="mx-auto w-full max-w-6xl space-y-6 p-6 md:p-10">
        <Suspense fallback={<Skeleton className="h-64 w-full" />}>
          {params.then(({ id }) => (
            <ProjectView id={id} />
          ))}
        </Suspense>
      </main>
    </>
  );
}

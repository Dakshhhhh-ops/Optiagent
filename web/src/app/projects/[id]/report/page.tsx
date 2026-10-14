import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import { ProjectReport } from "./project-report";

export const metadata: Metadata = { title: "Report" };

export default function ReportPage({ params }: PageProps<"/projects/[id]/report">) {
  return (
    <main className="mx-auto w-full max-w-4xl p-6 md:p-10 print:max-w-none print:p-0">
      <Suspense fallback={<Skeleton className="h-96 w-full" />}>
        {params.then(({ id }) => (
          <ProjectReport id={id} />
        ))}
      </Suspense>
    </main>
  );
}

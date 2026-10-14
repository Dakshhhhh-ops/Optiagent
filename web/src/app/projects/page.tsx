import type { Metadata } from "next";

import { AppHeader } from "@/components/app-header";

import { ProjectList } from "./project-list";

export const metadata: Metadata = { title: "Projects" };

export default function ProjectsPage() {
  return (
    <>
      <AppHeader title="Projects" />
      <main className="mx-auto w-full max-w-6xl space-y-6 p-6 md:p-10">
        <ProjectList />
      </main>
    </>
  );
}

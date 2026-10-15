import type { APIRequestContext } from "@playwright/test";

export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

/** Delete projects created by a test, so local databases stay clean. */
export async function deleteProject(request: APIRequestContext, url: string) {
  const id = url.split("/projects/")[1]?.split(/[/?#]/)[0];
  if (id) await request.delete(`${API_URL}/api/v1/projects/${id}`);
}

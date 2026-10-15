import { expect, test } from "@playwright/test";

import { deleteProject } from "./helpers";

test("sample data → mapping → traced formulation → verified plan → what-if @mobile", async ({
  page,
  request,
}) => {
  await page.goto("/problems/new");

  // 1. Data: the SunRay sample (3 silos, 4 mills; known optimum 435).
  await page.getByRole("button", { name: /SunRay Transport/ }).click();
  await expect(page.getByText("Your tables")).toBeVisible();

  // 2-3. Map columns (the suggested mapping) and review the model.
  await page.getByRole("button", { name: /Map columns manually/ }).click();
  const review = page.getByRole("button", { name: /Review model/ });
  await expect(review).toBeEnabled();
  await review.click();

  // 4-6. The formulation, with traceability: every number traced to the uploaded file.
  await expect(page.getByText("Requirement traceability")).toBeVisible();
  await expect(page.getByText("Traced", { exact: true })).toBeVisible();
  await page.getByText(/Where each number comes from/).click();
  await expect(page.getByText(/read by code from table/).first()).toBeVisible();

  // 7-8. Approve the exact formulation; the server solves, verifies and saves it.
  const approve = page.getByRole("button", { name: "Approve & solve" });
  await expect(approve).toBeEnabled();
  await approve.click();
  await page.waitForURL(/\/projects\/[0-9a-f]+$/);
  const projectUrl = page.url();

  try {
    await expect(page.getByText("435", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Plan verified").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Against your data" }).first()).toBeVisible();
    await expect(page.getByText("Proven optimal from your data (duality certificate)")).toBeVisible();

    // 9. What-if: change one number; the saved project is not touched.
    await page.locator("#whatif-value").fill("100");
    await page.getByRole("button", { name: /Re-solve/ }).click();
    await expect(page.getByText(/Scenario only/)).toBeVisible();

    // 10. The project is listed and has a printable report.
    await page.goto("/projects");
    await expect(page.locator(`a[href="${new URL(projectUrl).pathname}"]`).first()).toBeVisible();
    await page.goto(`${new URL(projectUrl).pathname}/report`);
    await expect(page.getByText(/plan verified optimal against the model and the data/)).toBeVisible();
  } finally {
    await deleteProject(request, projectUrl);
  }
});

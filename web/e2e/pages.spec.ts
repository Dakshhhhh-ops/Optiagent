import { expect, test } from "@playwright/test";

test("overview loads @mobile", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /verified/ }).first()).toBeVisible();
});

test("benchmarks show the deterministic verification results", async ({ page }) => {
  await page.goto("/benchmarks");
  await expect(page.getByText("Deterministic verification benchmark")).toBeVisible();
  await expect(page.getByText("flag everything (baseline)").first()).toBeVisible();
  await expect(page.getByText("Model-builder faults")).toBeVisible();
});

test("pages have no horizontal scroll @mobile", async ({ page }) => {
  for (const path of ["/", "/problems/new", "/benchmarks", "/projects"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(1);
  }
});

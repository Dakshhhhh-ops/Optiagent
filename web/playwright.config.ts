import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running web app and API (no AI calls).
 *
 *   E2E_BASE_URL=http://localhost:3000 E2E_API_URL=http://localhost:8001 pnpm e2e
 *
 * CI starts both servers itself, then runs these tests. Locally, E2E_CHANNEL=msedge (or chrome)
 * uses an installed browser instead of downloading Playwright's Chromium.
 */
const channel = process.env.E2E_CHANNEL;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel } },
    { name: "phone", use: { ...devices["Pixel 7"], channel }, grep: /@mobile/ },
  ],
});

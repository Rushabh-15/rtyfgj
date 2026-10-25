import { defineConfig, devices } from "@playwright/test";

// Smoke test against any running copy of the app: the local container in CI, or the deployed URL.
const baseURL = process.env.BASE_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});

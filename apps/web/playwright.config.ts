import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  // Browser tests share one local API; concurrent password hashing can exceed short UI waits.
  workers: 1,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3001", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});

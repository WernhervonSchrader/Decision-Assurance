import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  use: {
    baseURL: process.env.DA_PILOT_BASE_URL ?? "http://127.0.0.1:4173",
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.DA_PILOT_BASE_URL ? undefined : {
    command: "npm run preview:e2e",
    url: "http://127.0.0.1:4173/health/ready",
    reuseExistingServer: !process.env.CI,
  },
});

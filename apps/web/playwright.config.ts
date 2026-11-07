import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --app-dir ../api --host 127.0.0.1 --port 8000",
      env: { ...process.env, LLM_PROVIDER: "mock" },
      reuseExistingServer: !process.env.CI,
      url: "http://127.0.0.1:8000/api/v1/health",
    },
    {
      command: "pnpm dev",
      reuseExistingServer: !process.env.CI,
      url: "http://127.0.0.1:3000/audit",
    },
  ],
});

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Run up to 3 spec files in parallel. Each test gets its own seeded canvas
  // via the canvasWithWorkflow fixture (per-test scope), so there are no
  // shared-state conflicts. CI runners typically have 2–4 cores.
  workers: process.env.CI ? 3 : 1,
  reporter: [
    ["html"],
    ["junit", { outputFile: "junit/e2e-results.xml" }],
  ],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      // Backend: requires DATABASE_URL env var pointing to SQLite for CI
      command: "uv run alembic upgrade head && uv run uvicorn canvas_server.main:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: process.env.DATABASE_URL ?? "sqlite+aiosqlite:///./e2e_test.db",
        MLFLOW_ENABLED: process.env.MLFLOW_ENABLED ?? "false",
      },
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Authenticate once before the suite (register + login) and share the
  // session cookie with every test context via `use.storageState`. See
  // e2e/global-setup.ts.
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Run sequentially with 1 worker to prevent concurrent SQLite database write locks
  // and CPU overloading on CI runners.
  workers: 1,
  reporter: [
    ["list"],
    ["html"],
    ["junit", { outputFile: "junit/e2e-results.xml" }],
  ],
  use: {
    baseURL: "http://localhost:5173",
    // Injected by globalSetup — every browser context and `request` fixture
    // starts with the authenticated session cookie, so seeding canvases (API)
    // and driving the app (UI, behind the route guard) both work.
    storageState: "e2e/.auth/user.json",
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

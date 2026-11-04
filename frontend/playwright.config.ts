import { defineConfig, devices } from "@playwright/test";

/**
 * By default Playwright starts the API (uvicorn) and the built SPA (vite preview, which
 * proxies /api). Set E2E_BASE_URL to run against an already running stack, e.g. the
 * Docker Compose deployment (http://localhost:8080).
 */
const externalBaseUrl = process.env.E2E_BASE_URL;
const apiPort = Number(process.env.E2E_API_PORT ?? 8000);
const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: externalBaseUrl ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } } }],
  webServer: externalBaseUrl
    ? undefined
    : [
        {
          command: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
          cwd: "../backend",
          url: `http://127.0.0.1:${apiPort}/api/health`,
          reuseExistingServer: !isCI,
          timeout: 60_000,
          env: {
            FABTRACK_ENV: "test",
            FABTRACK_DATABASE_URL:
              process.env.FABTRACK_E2E_DATABASE_URL ??
              "postgresql+asyncpg://postgres:postgres@localhost:5432/fabtrack_e2e",
            FABTRACK_DATA_DIR: "./var/e2e-data",
          },
        },
        {
          command: "npm run build && npx vite preview",
          url: "http://127.0.0.1:4173",
          reuseExistingServer: !isCI,
          timeout: 120_000,
          env: { FABTRACK_API_URL: `http://127.0.0.1:${apiPort}` },
        },
      ],
});

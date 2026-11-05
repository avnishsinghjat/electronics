import type { Page } from "@playwright/test";

/** Fixed /api/health payload so visual snapshots do not depend on disk usage or latency. */
export const FIXED_HEALTH = {
  status: "ok",
  version: "0.0.1",
  environment: "production",
  air_gapped: true,
  database: { status: "ok", latency_ms: 2.4, detail: null },
  disk: { status: "ok", path: "/data", free_bytes: 412 * 1024 ** 3, total_bytes: 931 * 1024 ** 3, detail: null },
  llm: { status: "not_configured", provider: null, detail: "LLM gateway not configured (delivered in Phase 9)" },
};

export async function stubHealth(page: Page): Promise<void> {
  await page.route("**/api/health", (route) => route.fulfill({ json: FIXED_HEALTH }));
}

/** Wait for bundled fonts so text metrics are final before screenshots. */
export async function fontsReady(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

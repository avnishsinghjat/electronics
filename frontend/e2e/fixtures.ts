import { type Page, test as base, expect } from "@playwright/test";

/** Credentials of the administrator created by global-setup through the setup wizard. */
export const ADMIN = {
  username: process.env.E2E_ADMIN_USER ?? "admin",
  password: process.env.E2E_ADMIN_PASSWORD ?? "E2e-plant-pass-2026",
  fullName: "E2E Administrator",
};

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

type Fixtures = {
  /** Sign the browser context in before the test (via the API, which sets the refresh
   *  cookie). Each test gets its own session, because refresh tokens rotate and a reused
   *  token ends the session by design. `null` = anonymous. */
  loginAs: { username: string; password: string } | null;
};

export const test = base.extend<Fixtures>({
  loginAs: [ADMIN, { option: true }],
  context: async ({ context, loginAs }, use) => {
    if (loginAs) {
      const resp = await context.request.post("/api/auth/login", { data: loginAs });
      expect(resp.status(), await resp.text()).toBe(200);
    }
    await use(context);
  },
});

export { expect };

/** Admin API helper for arranging test data (e.g. users with temporary passwords). */
export async function adminApi(page: Page) {
  const resp = await page.request.post("/api/auth/refresh");
  expect(resp.status()).toBe(200);
  const { access_token } = (await resp.json()) as { access_token: string };
  const headers = { Authorization: `Bearer ${access_token}` };
  return {
    createUser: async (username: string, roles: string[]) => {
      const r = await page.request.post("/api/users", { headers, data: { username, full_name: `E2E ${username}`, roles } });
      expect(r.status(), await r.text()).toBe(201);
      return (await r.json()) as { temporary_password: string; user: { id: string } };
    },
  };
}

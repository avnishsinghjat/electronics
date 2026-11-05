import { expect, test } from "@playwright/test";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * CLAUDE.md rule 1: the app must work with the network cable unplugged.
 * Every non-local request is blocked AND recorded; the test fails if any was attempted.
 */
test("app loads with all non-localhost network blocked and attempts none", async ({ page, context }) => {
  const external: string[] = [];
  const local: string[] = [];

  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === "data:" || url.protocol === "blob:" || LOCAL_HOSTS.has(url.hostname)) {
      local.push(url.pathname);
      await route.continue();
    } else {
      external.push(route.request().url());
      await route.abort("blockedbyclient");
    }
  });
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (!["data:", "blob:"].includes(url.protocol) && !LOCAL_HOSTS.has(url.hostname)) {
      external.push(req.url());
    }
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  // Real round trip through the proxy to the API and PostgreSQL.
  const details = page.getByLabel("Health");
  await expect(details.getByText("Database")).toBeVisible();
  await expect(details.getByText("LLM gateway not configured (delivered in Phase 9)")).toBeVisible();
  await page.waitForLoadState("networkidle");

  // Bundled fonts are actually used (served from /fonts, not a CDN).
  const fontsReady = await page.evaluate(async () => {
    await document.fonts.ready;
    return {
      inter: document.fonts.check('16px "Inter"'),
      mono: document.fonts.check('16px "JetBrains Mono"'),
      loaded: [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family),
    };
  });
  expect(fontsReady.inter).toBe(true);
  expect(fontsReady.loaded).toContain("Inter");
  expect(fontsReady.loaded).toContain("JetBrains Mono");
  expect(local.some((p) => p.startsWith("/fonts/inter-"))).toBe(true);
  expect(local).toContain("/api/health");

  expect(external, `external requests attempted: ${external.join(", ")}`).toEqual([]);
});

test("health shows OK for database against the real API", async ({ page }) => {
  await page.goto("/");
  const dbRow = page.getByLabel("Health").locator("div", { has: page.getByText("Database", { exact: true }) });
  await expect(dbRow.getByText("ok", { exact: true })).toBeVisible();
});

test("every page of the shell loads offline, including lazy routes", async ({ page, context }) => {
  const external: string[] = [];
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (["data:", "blob:"].includes(url.protocol) || LOCAL_HOSTS.has(url.hostname)) await route.continue();
    else {
      external.push(url.href);
      await route.abort("blockedbyclient");
    }
  });
  for (const path of ["/", "/dev/ui", "/projects", "/qc", "/settings", "/missing"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).or(page.getByRole("heading", { name: "Page not found" }))).toBeVisible();
  }
  expect(external).toEqual([]);
});

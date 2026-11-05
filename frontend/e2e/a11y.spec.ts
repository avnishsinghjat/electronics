import AxeBuilder from "@axe-core/playwright";
import { expect, stubHealth, test } from "./fixtures";

const PAGES = ["/dev/ui", "/", "/projects", "/missing", "/settings/general", "/settings/users", "/settings/audit", "/change-password"];

for (const path of PAGES) {
  test(`axe: no serious or critical violations on ${path}`, async ({ page }) => {
    await stubHealth(page);
    await page.goto(path);
    await expect(page.getByRole("heading").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(
      serious.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s) e.g. ${v.nodes[0]?.target.join(" ")}`),
    ).toEqual([]);
  });
}

test("axe: open dialog and command palette are accessible", async ({ page }) => {
  await stubHealth(page);
  await page.goto("/dev/ui");
  await page.getByRole("button", { name: "Open dialog" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  let results = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  await page.keyboard.press("Escape");
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  results = await new AxeBuilder({ page }).include('[role="dialog"]').analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});

test.describe("anonymous pages", () => {
  test.use({ loginAs: null });

  test("axe: login page", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });
});

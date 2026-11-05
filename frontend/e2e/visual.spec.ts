import { expect, test } from "@playwright/test";

import { fontsReady, stubHealth } from "./fixtures";

const SIZES = [
  { width: 1366, height: 768 },
  { width: 1920, height: 1080 },
];

test.use({ timezoneId: "Asia/Kolkata", locale: "en-IN" });

for (const size of SIZES) {
  test.describe(`${size.width}x${size.height}`, () => {
    test.use({ viewport: size });

    test("shell: dashboard", async ({ page }) => {
      await stubHealth(page);
      await page.goto("/");
      await expect(page.getByText("2.4 ms")).toBeVisible();
      await fontsReady(page);
      await expect(page).toHaveScreenshot(`shell-dashboard-${size.width}.png`, { animations: "disabled" });
    });

    test("shell: collapsed sidebar on a roadmap section", async ({ page }) => {
      await stubHealth(page);
      await page.goto("/production");
      await page.getByRole("button", { name: "Collapse sidebar" }).click();
      await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
      await fontsReady(page);
      await expect(page).toHaveScreenshot(`shell-collapsed-${size.width}.png`, { animations: "disabled" });
    });

    test("dev/ui full page", async ({ page }) => {
      await stubHealth(page);
      await page.goto("/dev/ui");
      await expect(page.getByText("10,000 of 10,000 rows")).toBeVisible();
      await fontsReady(page);
      await expect(page).toHaveScreenshot(`dev-ui-${size.width}.png`, { fullPage: true, animations: "disabled" });
    });
  });
}

test("print stylesheet hides the app chrome", async ({ page }) => {
  await stubHealth(page);
  await page.goto("/dev/ui");
  await page.emulateMedia({ media: "print" });
  await expect(page.locator('aside[data-shell="sidebar"]')).toBeHidden();
  await expect(page.locator('header[data-shell="topbar"]')).toBeHidden();
  await expect(page.getByRole("heading", { level: 1, name: "UI kit" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show toast" })).toBeHidden();
});

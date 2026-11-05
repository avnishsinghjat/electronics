import path from "node:path";

import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./fixtures";

const DRAWING = path.join(import.meta.dirname, "fixtures-files", "assembly-drawing.pdf");

test("division → project → module → assembly, attach a file, see it in History", async ({ page }) => {
  const tag = Date.now().toString(36).toUpperCase().slice(-5);
  const divisionCode = `E2E${tag}`;

  await page.goto("/projects");
  await page.getByRole("button", { name: "Divisions" }).click();
  const divisions = page.getByRole("dialog", { name: "Divisions" });
  await divisions.getByRole("button", { name: "Add division" }).click();
  await divisions.getByLabel(/Code/).fill(divisionCode);
  await divisions.getByLabel(/^Name/).fill(`E2E Division ${tag}`);
  await divisions.getByRole("button", { name: "Add division" }).click();
  await expect(page.getByText("Division created")).toBeVisible();
  await expect(divisions.getByText(`E2E Division ${tag}`)).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "New project" }).first().click();
  const drawer = page.getByRole("dialog", { name: "New project" });
  await drawer.getByLabel(/Project name/).fill(`Motor controller ${tag}`);
  await drawer.getByLabel(/^Client\*?$/).fill("Godavari Packaging");
  await drawer.getByLabel("Client PO reference").fill(`GPM-${tag}`);
  await drawer.getByRole("combobox", { name: /Division/ }).click();
  await page.getByRole("option", { name: `E2E Division ${tag}` }).click();
  await drawer.getByLabel("Due date").fill("2027-03-31");
  await drawer.getByLabel("Due date").press("Enter");
  await drawer.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByRole("heading", { level: 1, name: `Motor controller ${tag}` })).toBeVisible();
  const code = (await page.getByText(/^PRJ-\d{4}-\d{4}$/).first().textContent()) ?? "";

  await page.getByRole("button", { name: "Add module" }).first().click();
  const md = page.getByRole("dialog", { name: "New module" });
  await md.getByLabel(/Code/).fill("MOD-MC");
  await md.getByLabel(/^Name/).fill("Motor controller unit");
  await md.getByLabel(/Quantity to deliver/).fill("40");
  await md.getByRole("button", { name: "Add module" }).click();
  const module = page.getByRole("region", { name: "Module MOD-MC" });
  await expect(module).toBeVisible();

  await module.getByRole("button", { name: /Assembly/ }).click();
  const ad = page.getByRole("dialog", { name: "New PCB assembly" });
  await ad.getByLabel(/Assembly code/).fill("MCB");
  await ad.getByLabel(/Board name/).fill("Motor control board");
  await ad.getByLabel("Width").fill("120");
  await ad.getByLabel("Height").fill("90");
  await ad.getByRole("button", { name: "Add assembly" }).click();
  await expect(module.getByText("Motor control board")).toBeVisible();

  // Attach the assembly drawing and link it.
  await module.getByRole("button", { name: "Edit assembly MCB rev A" }).click();
  const edit = page.getByRole("dialog", { name: "Edit MCB rev A" });
  await edit.locator('input[type="file"]').setInputFiles(DRAWING);
  await expect(page.getByText("1 file attached")).toBeVisible();
  await expect(edit.getByRole("list", { name: "Assembly files list" }).getByText("assembly-drawing.pdf")).toBeVisible();
  await edit.getByRole("combobox", { name: "Assembly drawing" }).click();
  await page.getByRole("option", { name: "assembly-drawing.pdf" }).click();
  await edit.getByRole("button", { name: "Save assembly" }).click();
  await expect(module.getByRole("cell", { name: "Drawing" })).toBeVisible();

  await page.getByRole("tab", { name: "History" }).click();
  const history = page.getByRole("tabpanel", { name: "History" });
  await expect(history.getByText("File assembly-drawing.pdf created")).toBeVisible();
  await expect(history.getByText("Assembly MCB rev A updated")).toBeVisible();
  await expect(history.getByText("Module MOD-MC created")).toBeVisible();
  await expect(history.getByText(`Project ${code} created`)).toBeVisible();

  // The new project is listed under its division.
  await page.goto("/projects");
  const section = page.getByRole("region", { name: new RegExp(`E2E Division ${tag}`) });
  await expect(section.getByRole("link", { name: code })).toBeVisible();
});

test("axe: projects list and a project page", async ({ page }) => {
  await page.goto("/projects");
  await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  let results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  const first = page.getByRole("link", { name: /^PRJ-/ }).first();
  if (await first.count()) {
    await first.click();
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
    results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  }
});

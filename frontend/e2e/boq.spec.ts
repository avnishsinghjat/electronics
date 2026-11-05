import path from "node:path";

import AxeBuilder from "@axe-core/playwright";

import { adminApi, expect, test } from "./fixtures";

const SAMPLES = path.join(import.meta.dirname, "..", "..", "samples");
const MESSY = path.join(SAMPLES, "boq-messy.csv");
const CLEAN_A = path.join(SAMPLES, "boq-clean.csv");
const CLEAN_B = path.join(SAMPLES, "boq-clean-rev-b.csv");

/** A fresh division + project per test so runs never collide. */
async function newProject(page: Parameters<typeof adminApi>[0]) {
  const api = await adminApi(page);
  const tag = Date.now().toString(36).toUpperCase().slice(-5) + Math.floor(Math.random() * 36 ** 2).toString(36).toUpperCase();
  const division = await api.post<{ id: string }>("/divisions", { code: `B${tag}`, name: `BOQ E2E ${tag}` });
  return api.post<{ id: string; code: string }>("/projects", { division_id: division.id, name: `Motor driver ${tag}`, client_name: "ACME Industrial", status: "active" });
}

test("upload messy CSV, fix mapping, see errors, upload clean CSV, commit, compare Rev A vs Rev B", async ({ page }) => {
  test.setTimeout(90_000);
  const project = await newProject(page);
  await page.goto(`/projects/${project.id}?tab=boq`);
  const panel = page.getByRole("tabpanel", { name: "BOQ" });

  await panel.getByRole("button", { name: "New BOQ" }).click();
  const create = page.getByRole("dialog", { name: "New BOQ" });
  await create.getByLabel(/Name/).fill("Motor driver BOM");
  await create.getByRole("button", { name: "Create and import file" }).click();
  await expect(page.getByText("BOQ “Motor driver BOM” created")).toBeVisible();

  // 1. The messy client file: Windows-1252, title rows above the header.
  const wizard = page.getByRole("dialog", { name: "Import BOQ" });
  await wizard.locator('input[type="file"]').setInputFiles(MESSY);
  const mapping = wizard.getByRole("table", { name: "Column mapping" });
  await expect(mapping).toBeVisible();
  await expect(wizard.getByText("Encoding windows-1252")).toBeVisible();
  await expect(wizard.getByRole("combobox", { name: "Header row" })).toContainText("Row 4: Item | Designator | Quantity | Mfr Part Number");
  await expect(mapping.getByRole("combobox", { name: "Column for MPN" })).toContainText("D: Mfr Part Number");

  // A wrong mapping (MPN column left out) flags every row, then the mapping is fixed.
  await mapping.getByRole("combobox", { name: "Column for MPN" }).click();
  await page.getByRole("option", { name: "— not in file —" }).click();
  await wizard.getByRole("button", { name: "Validate file" }).click();
  const banner = wizard.getByRole("status").filter({ hasText: /must be fixed/ });
  await expect(banner).toContainText("14 errors");
  await expect(wizard.getByRole("button", { name: "Commit as new revision" })).toBeDisabled();
  await wizard.getByRole("button", { name: "Change mapping" }).click();
  await mapping.getByRole("combobox", { name: "Column for MPN" }).click();
  await page.getByRole("option", { name: "D: Mfr Part Number" }).click();
  await wizard.getByRole("button", { name: "Validate file" }).click();

  // Now only the file's own problems are listed, and they still block the commit.
  await expect(banner).toContainText("5 errors");
  const issues = wizard.getByRole("table").filter({ hasText: "Problem" });
  await expect(issues.getByRole("cell", { name: "invalid_qty" }).first()).toBeVisible();
  await expect(issues.getByRole("cell", { name: "missing_mpn" })).toHaveCount(1);
  await expect(issues.getByRole("cell", { name: "duplicate_ref_des" }).first()).toBeVisible();
  await expect(wizard.getByRole("button", { name: "Commit as new revision" })).toBeDisabled();
  const download = page.waitForEvent("download");
  await wizard.getByRole("button", { name: "Error report CSV" }).click();
  expect((await download).suggestedFilename()).toBe("boq-messy-import-report.csv");
  await page.keyboard.press("Escape");
  await expect(wizard).toBeHidden();

  // 2. The clean file commits as revision A and is released.
  await panel.getByRole("button", { name: "Import file" }).click();
  await wizard.locator('input[type="file"]').setInputFiles(CLEAN_A);
  await wizard.getByRole("button", { name: "Validate file" }).click();
  await expect(wizard.getByText(/^No errors\./)).toBeVisible();
  await wizard.getByLabel("Build quantity").fill("50");
  await wizard.getByLabel("Release the revision immediately").check();
  await wizard.getByRole("button", { name: "Commit as new revision" }).click();
  await expect(page.getByText(/Revision A created with 15 lines/)).toBeVisible();
  await expect(panel.getByRole("tab", { name: /Rev A/ })).toContainText("released");
  await expect(panel.getByText("Read-only: start a new revision to change it")).toBeVisible();
  await expect(panel.getByRole("row", { name: /GRM188R71H104KA93D/ })).toContainText("Not ordered");

  // 3. Revision B from the client's updated file.
  await panel.getByRole("button", { name: "Import file" }).click();
  await wizard.locator('input[type="file"]').setInputFiles(CLEAN_B);
  await wizard.getByRole("button", { name: "Validate file" }).click();
  await expect(wizard.getByText(/^No errors\./)).toBeVisible();
  await wizard.getByRole("button", { name: "Commit as new revision" }).click();
  await expect(page.getByText(/Revision B created with/)).toBeVisible();
  await expect(panel.getByRole("tab", { name: /Rev B/ })).toContainText("draft");
  await expect(panel.getByRole("grid", { name: "BOQ lines editor" })).toBeVisible();

  // 4. Compare A vs B.
  await panel.getByRole("button", { name: "Compare" }).click();
  const compare = page.getByRole("dialog", { name: "Compare revisions of Motor driver BOM" });
  const summary = compare.getByLabel("Change summary");
  await expect(summary).toContainText("Added: 1");
  await expect(summary).toContainText("Removed: 1");
  await expect(summary).toContainText("Qty changed: 1");
  await expect(summary).toContainText("Part substituted: 1");
  await expect(compare.getByRole("row", { name: /Qty changed/ }).first()).toContainText("GRM188R71H104KA93D");
});

test("edit a draft revision in the grid and release it", async ({ page }) => {
  const project = await newProject(page);
  await page.goto(`/projects/${project.id}?tab=boq`);
  const panel = page.getByRole("tabpanel", { name: "BOQ" });
  await panel.getByRole("button", { name: "New BOQ" }).click();
  const create = page.getByRole("dialog", { name: "New BOQ" });
  await create.getByLabel(/Name/).fill("Hand-typed BOM");
  await create.getByRole("button", { name: "Start empty" }).click();

  await panel.getByRole("button", { name: "Add row" }).click();
  const grid = panel.getByRole("grid", { name: "BOQ lines editor" });
  await grid.getByLabel("Ref des, line 1").fill("R1-R3");
  await grid.getByLabel("Qty / unit, line 1").fill("3");
  await grid.getByLabel("MPN, line 1").fill("RC0603FR-0710KL");
  await grid.getByLabel("Description, line 1").fill("Res 10k 0603");
  await grid.getByLabel("Category, line 1").fill("Passive");
  await grid.getByLabel("Category, line 1").press("Enter");
  await expect(grid.getByLabel("Category, line 2")).toBeFocused();
  await grid.getByLabel("Ref des, line 2").fill("U1");
  await grid.getByLabel("Qty / unit, line 2").fill("1");
  await grid.getByLabel("MPN, line 2").fill("LM358DR");
  await grid.getByLabel("Description, line 2").fill("Dual op-amp");
  await panel.getByRole("button", { name: "Save lines" }).click();
  await expect(page.getByText("BOQ lines saved")).toBeVisible();

  await panel.getByLabel("Build quantity").fill("10");
  await panel.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Build quantity and attrition saved")).toBeVisible();

  await panel.getByRole("button", { name: "Release revision" }).click();
  await expect(page.getByText("Revision A released")).toBeVisible();
  // 3 per unit x 10 units x (1 + passive attrition) rounded up; the server computes it.
  const row = panel.getByRole("row", { name: /RC0603FR-0710KL/ });
  await expect(row).toContainText("Not ordered");
  await expect(panel.getByRole("button", { name: "New revision" })).toBeVisible();
});

test("axe: BOQ tab and the import wizard", async ({ page }) => {
  const project = await newProject(page);
  await page.goto(`/projects/${project.id}?tab=boq`);
  const panel = page.getByRole("tabpanel", { name: "BOQ" });
  await panel.getByRole("button", { name: "New BOQ" }).click();
  const create = page.getByRole("dialog", { name: "New BOQ" });
  await create.getByLabel(/Name/).fill("A11y BOM");
  await create.getByRole("button", { name: "Create and import file" }).click();
  const wizard = page.getByRole("dialog", { name: "Import BOQ" });
  await wizard.locator('input[type="file"]').setInputFiles(MESSY);
  await expect(wizard.getByRole("table", { name: "Column mapping" })).toBeVisible();
  const mappingScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(mappingScan.violations).toEqual([]);
  await wizard.getByRole("button", { name: "Validate file" }).click();
  await expect(wizard.getByRole("button", { name: "Error report CSV" })).toBeVisible();
  const reviewScan = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(reviewScan.violations).toEqual([]);
});

import { expect, test } from "./fixtures";

test("admin creates a user, sees it audited, and the diff view", async ({ page }) => {
  await page.goto("/settings/users");
  await page.getByRole("button", { name: "New user" }).click();
  const drawer = page.getByRole("dialog", { name: "New user" });
  await drawer.getByLabel(/Username/).fill("e2e_qc_lead");
  await drawer.getByLabel(/Full name/).fill("Meena QC Lead");
  await drawer.getByRole("checkbox", { name: /QC Lead/ }).click();
  await drawer.getByRole("button", { name: "Create user" }).click();
  const dlg = page.getByRole("dialog", { name: "Temporary password" });
  await expect(dlg.getByTestId("temporary-password")).toHaveText(/^[A-Za-z0-9]{4}(-[A-Za-z0-9]{4}){3}$/);
  await dlg.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("cell", { name: "e2e_qc_lead", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Audit log" }).click();
  await page.getByRole("combobox", { name: "Record type" }).click();
  await page.getByRole("option", { name: "user_roles" }).click();
  await expect(page.getByRole("cell", { name: "Created" }).first()).toBeVisible();
  await page.getByRole("button", { name: /^View change/ }).first().click();
  const diff = page.getByRole("table", { name: "Field changes" });
  await expect(diff.getByRole("cell", { name: "qc_lead" })).toBeVisible();
});

test("admin changes a document prefix", async ({ page }) => {
  await page.goto("/settings/general");
  const prefix = page.getByLabel("Prefix for Work order");
  await prefix.fill("JOB");
  await expect(page.getByText(/^JOB-\d{4}-0001$/)).toBeVisible();
  await page.getByRole("row", { name: /Work order/ }).getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Work order prefix set to JOB")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Prefix for Work order")).toHaveValue("JOB");
  // put it back so re-runs on the same database see the default
  await page.getByLabel("Prefix for Work order").fill("WO");
  await page.getByRole("row", { name: /Work order/ }).getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Work order prefix set to WO")).toBeVisible();
});

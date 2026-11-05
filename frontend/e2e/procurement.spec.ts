import AxeBuilder from "@axe-core/playwright";

import { adminApi, expect, test } from "./fixtures";

type Api = Awaited<ReturnType<typeof adminApi>>;

/** A project whose released BOQ needs two parts, plus a vendor; arranged via the API. */
async function arrange(api: Api, tag: string) {
  const division = await api.post<{ id: string }>("/divisions", { code: `P${tag}`, name: `Purchasing ${tag}` });
  const project = await api.post<{ id: string; code: string }>("/projects", {
    division_id: division.id, name: `Drive controller ${tag}`, client_name: "Godavari Packaging", status: "active",
  });
  const module = await api.post<{ id: string }>(`/projects/${project.id}/modules`, { code: "MOD-DRV", name: "Drive module", qty_to_deliver: 10 });
  const res = await api.post<{ id: string; mpn: string }>("/parts", { mpn: `RES-${tag}`, manufacturer: "Yageo", description: "Res 10k 0603", category: "Passive" });
  const mcu = await api.post<{ id: string; mpn: string }>("/parts", { mpn: `MCU-${tag}`, manufacturer: "ST", description: "MCU LQFP-48", category: "IC" });
  const vendor = await api.post<{ id: string; name: string }>("/vendors", { code: `V${tag}`, name: `Deccan Components ${tag}`, payment_terms: "30 days", lead_time_days: 7 });
  const boq = await api.post<{ id: string; revisions: { id: string; row_version: number }[] }>(`/projects/${project.id}/boqs`, {
    name: "Drive board BOM", module_id: module.id, build_qty: 10,
  });
  const rev = boq.revisions[0]!;
  const line = (p: { id: string; mpn: string }, qtyPer: string, category: string) => ({
    line_key: null, part_id: p.id, ref_des: null, qty_per_unit: qtyPer, mpn: p.mpn, manufacturer: null, description: null,
    value: null, package: null, category, unit: "pcs", dnp: false, attrition_pct: "0", unit_price: null, notes: null,
  });
  const saved = await api.put<{ row_version: number }>(`/boq-revisions/${rev.id}/lines`, {
    row_version: rev.row_version, lines: [line(res, "10", "Passive"), line(mcu, "1", "IC")],
  });
  await api.post(`/boq-revisions/${rev.id}/release`, { row_version: saved.row_version });
  return { project, res, mcu, vendor };
}

test("shortfall → PR → PO → partial GRN → Partially received → final GRN → Received", async ({ page }) => {
  test.setTimeout(120_000);
  const tag = Date.now().toString(36).toUpperCase().slice(-6);
  const { project, res, mcu, vendor } = await arrange(await adminApi(page), tag);

  // 1. The tracker shows the shortfall; requisition all of it.
  await page.goto(`/projects/${project.id}?tab=procurement`);
  const panel = page.getByRole("tabpanel", { name: "Procurement" });
  await expect(panel.getByLabel("Tracker summary")).toContainText("Lines to order2");
  await expect(panel.getByRole("row", { name: new RegExp(res.mpn) })).toContainText("Not ordered");
  await panel.getByRole("button", { name: "Requisition all shortfall" }).click();
  await expect(page.getByText(/Requisition PR-\d{4}-\d{4} raised with 2 lines/)).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: /Requisition PR-/ })).toBeVisible();

  // 2. Pick the vendor, submit, approve, convert.
  for (const p of [res, mcu]) {
    await page.getByRole("combobox", { name: `Vendor for ${p.mpn}` }).click();
    await page.getByRole("option", { name: vendor.name }).click();
  }
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Requisition saved")).toBeVisible();
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText("Awaiting approval")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create purchase orders" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /^PO-\d{4}-\d{4}$/ })).toBeVisible();
  const poNumber = (await page.getByRole("heading", { level: 1 }).textContent()) ?? "";

  // 3. Prices on the draft, then issue.
  await page.getByRole("button", { name: "Edit" }).click();
  const editor = page.getByRole("dialog", { name: `Edit ${poNumber}` });
  await editor.getByRole("listitem", { name: "PO line 1" }).getByLabel("Unit price ₹").fill("0.12");
  await editor.getByRole("listitem", { name: "PO line 2" }).getByLabel("Unit price ₹").fill("410");
  await editor.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText(`${poNumber} saved`)).toBeVisible();
  await page.getByRole("button", { name: "Issue to vendor" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Issue order" }).click();
  await expect(page.getByText("Issued", { exact: true }).first()).toBeVisible();

  // 4. Partial delivery: 60 of 100 resistors, all 10 MCUs (to the MSL cabinet by default if MSL > 1).
  await page.getByRole("button", { name: "Receive goods" }).click();
  const recv = page.getByRole("dialog", { name: `Receive goods on ${poNumber}` });
  await recv.getByLabel("Vendor delivery note").fill(`DN-${tag}-1`);
  await recv.getByLabel("Received, line 1").fill("60");
  await recv.getByLabel("Lot, line 1").fill("L2611");
  await recv.getByLabel("Received, line 2").fill("10");
  await recv.getByRole("button", { name: "Post goods receipt" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Goods receipt GRN-/ })).toBeVisible();

  await page.goto(`/projects/${project.id}?tab=procurement`);
  const resRow = panel.getByRole("row", { name: new RegExp(res.mpn) });
  await expect(resRow).toContainText("Partially received");
  await expect(resRow.getByRole("cell").filter({ hasText: /^60$/ })).toHaveCount(1); // received
  await expect(resRow.getByRole("cell").filter({ hasText: /^40$/ })).toHaveCount(1); // awaiting
  await expect(panel.getByRole("row", { name: new RegExp(mcu.mpn) })).toContainText("Received");
  await expect(panel.getByLabel("Clear to build by module")).toContainText("not clear");

  // 5. Final delivery.
  await resRow.getByRole("link", { name: poNumber }).click();
  await page.getByRole("button", { name: "Receive goods" }).click();
  await recv.getByLabel("Received, line 1").fill("40");
  await recv.getByRole("button", { name: "Post goods receipt" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Goods receipt GRN-/ })).toBeVisible();

  await page.goto(`/projects/${project.id}?tab=procurement`);
  await expect(panel.getByRole("row", { name: new RegExp(res.mpn) })).toContainText("Received");
  await expect(panel.getByLabel("Tracker summary")).toContainText("100%");
  await expect(panel.getByLabel("Clear to build by module")).toContainText("clear to build");

  // The stock is on the inventory page, reserved for the project.
  await page.goto("/inventory");
  const stockRow = page.getByRole("row", { name: new RegExp(res.mpn) });
  await expect(stockRow).toContainText("100");
});

test("axe: tracker, procurement lists and a purchase order", async ({ page }) => {
  const tag = Date.now().toString(36).toUpperCase().slice(-6);
  const api = await adminApi(page);
  const { project, res, vendor } = await arrange(api, `X${tag}`.slice(0, 6));
  await page.goto(`/projects/${project.id}?tab=procurement`);
  await expect(page.getByLabel("Tracker summary")).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

  const po = await api.post<{ id: string }>("/purchase-orders", {
    vendor_id: vendor.id, lines: [{ part_id: res.id, qty_ordered: "5", unit_price: "1.00", expected_date: null, notes: null, allocations: [] }],
  });
  await page.goto(`/procurement/orders/${po.id}`);
  await expect(page.getByRole("button", { name: "Issue to vendor" })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);

  for (const tab of ["", "?tab=orders", "?tab=vendors"]) {
    await page.goto(`/procurement${tab}`);
    await expect(page.getByRole("table").first()).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  }
  await page.goto("/inventory?tab=ledger");
  await expect(page.getByRole("table").first()).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
});

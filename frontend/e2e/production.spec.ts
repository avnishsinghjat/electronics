import AxeBuilder from "@axe-core/playwright";

import { adminApi, expect, test } from "./fixtures";

type Api = Awaited<ReturnType<typeof adminApi>>;

/** A board with a 3-stage template, a released BOQ and every part received (clear to
 *  build); arranged through the API. */
async function arrange(api: Api, tag: string) {
  const template = await api.post<{ id: string; row_version: number; name: string }>("/stage-templates", { name: `Quick build ${tag}` });
  await api.put(`/stage-templates/${template.id}`, {
    row_version: template.row_version,
    name: template.name,
    steps: [
      { stage_code: "kitting", name: "Kitting", requires_qc: false },
      { stage_code: "smt", name: "SMT placement", requires_qc: false },
      { stage_code: "packing", name: "Packing", requires_qc: false },
    ],
  });
  const division = await api.post<{ id: string }>("/divisions", { code: `W${tag}`, name: `Works ${tag}` });
  const project = await api.post<{ id: string; code: string }>("/projects", { division_id: division.id, name: `Sensor hub ${tag}`, client_name: "Godavari Packaging", status: "active" });
  const module = await api.post<{ id: string }>(`/projects/${project.id}/modules`, { code: "MOD-SH", name: "Sensor hub", qty_to_deliver: 2 });
  const assembly = await api.post<{ id: string; code: string }>(`/modules/${module.id}/assemblies`, { code: `SH${tag}`.slice(0, 12), board_name: "Sensor hub board", revision: "A", stage_template_id: template.id });
  const res = await api.post<{ id: string; mpn: string }>("/parts", { mpn: `R10K-${tag}`, manufacturer: "Yageo", description: "Res 10k", category: "Passive" });
  const mcu = await api.post<{ id: string; mpn: string }>("/parts", { mpn: `MCU-${tag}`, manufacturer: "ST", description: "MCU", category: "IC" });
  const vendor = await api.post<{ id: string }>("/vendors", { code: `VP${tag}`, name: `Plant vendor ${tag}` });
  const boq = await api.post<{ revisions: { id: string; row_version: number }[] }>(`/projects/${project.id}/boqs`, { name: "Hub BOM", module_id: module.id, build_qty: 2 });
  const rev = boq.revisions[0]!;
  const line = (p: { id: string; mpn: string }, q: string, category: string) => ({
    line_key: null, part_id: p.id, ref_des: null, qty_per_unit: q, mpn: p.mpn, manufacturer: null, description: null,
    value: null, package: null, category, unit: "pcs", dnp: false, attrition_pct: "0", unit_price: null, notes: null,
  });
  const saved = await api.put<{ row_version: number }>(`/boq-revisions/${rev.id}/lines`, { row_version: rev.row_version, lines: [line(res, "4", "Passive"), line(mcu, "1", "IC")] });
  await api.post(`/boq-revisions/${rev.id}/release`, { row_version: saved.row_version });
  const detail = await api.get<{ lines: { id: string; mpn: string }[] }>(`/boq-revisions/${rev.id}`);
  const lineId = (mpn: string) => detail.lines.find((l) => l.mpn === mpn)!.id;
  let po = await api.post<{ id: string; row_version: number; lines: { id: string }[] }>("/purchase-orders", {
    vendor_id: vendor.id,
    lines: [
      { part_id: res.id, qty_ordered: "8", unit_price: "0.10", expected_date: null, notes: null, allocations: [{ boq_line_id: lineId(res.mpn), qty: "8" }] },
      { part_id: mcu.id, qty_ordered: "2", unit_price: "300", expected_date: null, notes: null, allocations: [{ boq_line_id: lineId(mcu.mpn), qty: "2" }] },
    ],
  });
  po = await api.post(`/purchase-orders/${po.id}/issue`, { row_version: po.row_version });
  const locations = await api.get<{ id: string; code: string }[]>("/inventory/locations");
  const stores = locations.find((l) => l.code === "STORES")!.id;
  await api.post("/goods-receipts", {
    purchase_order_id: po.id,
    lines: [
      { po_line_id: po.lines[0]!.id, location_id: stores, qty_received: "8", qty_accepted: "8", batch_lot: `RL-${tag}` },
      { po_line_id: po.lines[1]!.id, location_id: stores, qty_received: "2", qty_accepted: "2", batch_lot: `ML-${tag}` },
    ],
  });
  return { project, assembly, res, mcu };
}

test.describe("on a tablet", () => {
  test.use({ viewport: { width: 1024, height: 768 }, hasTouch: true });

  test("release WO → kit → progress through 3 stages on the shop floor", async ({ page }) => {
    test.setTimeout(120_000);
    const tag = Date.now().toString(36).toUpperCase().slice(-6);
    const { project, res, mcu } = await arrange(await adminApi(page), tag);

    // Create the work order from the project's Production tab.
    await page.goto(`/projects/${project.id}?tab=production`);
    const panel = page.getByRole("tabpanel", { name: "Production" });
    await panel.getByRole("button", { name: "New work order" }).click();
    const drawer = page.getByRole("dialog", { name: "New work order" });
    await drawer.getByRole("combobox", { name: /PCB assembly/ }).click();
    await page.getByRole("option", { name: /Sensor hub board/ }).click();
    await drawer.getByLabel(/Build quantity/).fill("2");
    await drawer.getByRole("button", { name: "Create work order" }).click();
    await expect(page.getByRole("heading", { level: 1, name: /Work order WO-/ })).toBeVisible();
    await expect(page.getByText("Clear to build: every part is in stores.")).toBeVisible();

    // Release.
    await page.getByRole("button", { name: "Release to production" }).click();
    await page.getByRole("dialog", { name: /Release WO-/ }).getByRole("button", { name: "Release" }).click();
    await expect(page.getByText(/released to production/)).toBeVisible();

    // Kit both lines (lots are suggested), then check Issued reached the tracker.
    await page.getByRole("tab", { name: "Kitting" }).click();
    for (const p of [res, mcu]) {
      await page.getByRole("row", { name: new RegExp(p.mpn) }).getByRole("button", { name: "Issue" }).click();
      await page.getByRole("dialog", { name: `Issue ${p.mpn}` }).getByRole("button", { name: "Issue" }).click();
      await expect(page.getByText(new RegExp(`× ${p.mpn} issued`))).toBeVisible();
    }
    await expect(page.getByText("Fully kitted")).toBeVisible();

    // Serial numbers.
    await page.getByRole("tab", { name: "Units and stages" }).click();
    await page.getByRole("button", { name: /Generate 2 serial numbers/ }).click();
    await expect(page.getByText("2 serial numbers ready")).toBeVisible();
    const firstSerial = page.getByRole("cell", { name: /-\d{4}-\d{5}$/ }).first();
    await expect(firstSerial).toBeVisible(); // the table refetches after the toast
    const serial = (await firstSerial.textContent())!.trim();

    // Shop floor: scan (type) the serial and walk it through the 3 stages.
    await page.getByRole("link", { name: "Shop-floor mode" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Shop floor" })).toBeVisible();
    const input = page.getByLabel("Serial number");
    for (const stage of ["Kitting", "SMT placement", "Packing"]) {
      await input.fill(serial);
      await input.press("Enter");
      const card = page.getByRole("region", { name: `Unit ${serial}` });
      await expect(card).toContainText(stage);
      await card.getByRole("button", { name: `Start stage for ${serial}` }).click();
      await expect(page.getByText(`${serial}: ${stage} started`)).toBeVisible();
      await card.getByRole("button", { name: `Pass ${serial}` }).click();
      await expect(page.getByText(`${serial}: ${stage} passed`)).toBeVisible();
    }
    await expect(page.getByRole("region", { name: `Unit ${serial}` })).toContainText("All stages complete");
    await expect(page.getByRole("region", { name: `Unit ${serial}` })).toContainText("Passed");

    // Back on the project: Issued shows on the tracker.
    await page.goto(`/projects/${project.id}?tab=procurement`);
    await expect(page.getByRole("row", { name: new RegExp(res.mpn) })).toContainText("Issued");
  });
});

test("axe: production board, work order and shop floor", async ({ page }) => {
  const tag = Date.now().toString(36).toUpperCase().slice(-6);
  const api = await adminApi(page);
  const { assembly } = await arrange(api, `A${tag}`.slice(0, 6));
  const wo = await api.post<{ id: string }>("/work-orders", { assembly_id: assembly.id, build_qty: 1 });
  for (const url of ["/production", `/production/work-orders/${wo.id}`, "/production?tab=templates", "/shop-floor"]) {
    await page.goto(url);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  }
});

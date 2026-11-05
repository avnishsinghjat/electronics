import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { type Handler, makeMe, mockApi, renderAt, signedInRoutes } from "./utils";

function base(extra: Record<string, Handler> = {}) {
  return signedInRoutes(makeMe(), { "GET /divisions": () => [], ...extra });
}

const LOCATIONS = [
  { id: "loc-s", code: "STORES", name: "Main stores", kind: "stores", parent_id: null },
  { id: "loc-m", code: "MSL-DRY-1", name: "MSL dry cabinet", kind: "msl_cabinet", parent_id: null },
];

describe("Inventory", () => {
  it("flags low stock, and hides approve on one's own adjustment request", async () => {
    let decided: unknown = null;
    mockApi(
      base({
        "GET /inventory/stock": () => [
          { part_id: "pt1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", description: "Res", category: "Passive", unit: "pcs", msl_level: null, min_stock: 500, on_hand: "300", usable: "300", reserved: "100", available: "200", low: true, locations: ["STORES"], row_version: 1 },
        ],
        "GET /inventory/adjustments": () => [
          { id: "a1", part_id: "pt1", mpn: "RC0603FR-0710KL", location_id: "loc-s", location_code: "STORES", qty_delta: "-3", reason: "Count", lot_code: null, status: "pending", requested_by: "u-admin", requested_by_name: "Plant Admin", requested_at: "2026-11-05T05:00:00Z", decided_by_name: null, decided_at: null, decision_note: null, row_version: 1 },
          { id: "a2", part_id: "pt1", mpn: "GRM188R71H104KA93D", location_id: "loc-s", location_code: "STORES", qty_delta: "5", reason: "Found", lot_code: null, status: "pending", requested_by: "u-stores", requested_by_name: "Store Keeper", requested_at: "2026-11-05T05:00:00Z", decided_by_name: null, decided_at: null, decision_note: null, row_version: 2 },
        ],
        "POST /inventory/adjustments/a2/decision": ({ body }) => {
          decided = body;
          return {};
        },
      }),
    );
    renderAt("/inventory");
    const row = await screen.findByRole("row", { name: /RC0603FR-0710KL/ });
    expect(within(row).getByText("Low")).toBeInTheDocument();
    expect(within(row).getByText("200")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Adjustments" }));
    expect(await screen.findByRole("button", { name: "Approve adjustment of GRM188R71H104KA93D" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve adjustment of RC0603FR-0710KL" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve adjustment of GRM188R71H104KA93D" }));
    await waitFor(() => expect(decided).toEqual({ row_version: 2, approve: true, note: null }));
  });
});

describe("Inventory actions", () => {
  const BAL = [{ part_id: "pt1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", description: "Res", category: "Passive", unit: "pcs", msl_level: null, location_id: "loc-s", location_code: "STORES", location_kind: "stores", qty_on_hand: "300" }];

  it("moves stock and requests a counted adjustment", { timeout: 20_000 }, async () => {
    let moved: unknown = null;
    let requested: unknown = null;
    mockApi(
      base({
        "GET /inventory/locations": () => LOCATIONS,
        "GET /inventory/balances": () => BAL,
        "POST /inventory/transfers": ({ body }) => {
          moved = body;
          return [];
        },
        "POST /inventory/adjustments": ({ body }) => {
          requested = body;
          return {};
        },
      }),
    );
    renderAt("/inventory?tab=locations");
    await userEvent.click(await screen.findByRole("button", { name: "Move RC0603FR-0710KL from STORES" }));
    let dialog = await screen.findByRole("dialog", { name: "Move RC0603FR-0710KL" }, { timeout: 5000 });
    await userEvent.click(within(dialog).getByRole("button", { name: "Move stock" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Choose the destination");
    await userEvent.click(within(dialog).getByRole("combobox", { name: /To location/ }));
    await userEvent.click(await screen.findByRole("option", { name: /MSL-DRY-1/ }));
    await userEvent.type(within(dialog).getByLabelText(/Quantity/), "20");
    await userEvent.type(within(dialog).getByLabelText(/Note/), "Bake out");
    await userEvent.click(within(dialog).getByRole("button", { name: "Move stock" }));
    await waitFor(() => expect(moved).toEqual({ part_id: "pt1", from_location_id: "loc-s", to_location_id: "loc-m", qty: "20", lot_code: null, note: "Bake out" }));

    await userEvent.click(screen.getByRole("button", { name: "Adjust RC0603FR-0710KL at STORES" }));
    dialog = await screen.findByRole("dialog", { name: "Adjust RC0603FR-0710KL at STORES" }, { timeout: 5000 });
    await userEvent.type(within(dialog).getByLabelText(/Counted/), "297");
    expect(within(dialog).getByText("-3")).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Cycle count");
    await userEvent.click(within(dialog).getByRole("button", { name: "Request adjustment" }));
    await waitFor(() => expect(requested).toEqual({ part_id: "pt1", location_id: "loc-s", qty_delta: "-3", reason: "Cycle count", lot_code: null }));
  });

  it("reserves free stock for a project, sets minimum stock, lists the ledger and releases reservations", { timeout: 20_000 }, async () => {
    let reserved: unknown = null;
    let minimum: unknown = null;
    let released: unknown = null;
    mockApi(
      base({
        "GET /inventory/stock": () => [
          { part_id: "pt1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", description: "Res", category: "Passive", unit: "pcs", msl_level: null, min_stock: null, on_hand: "300", usable: "300", reserved: "0", available: "300", low: false, locations: ["STORES"], row_version: 4 },
        ],
        "GET /projects": () => ({ items: [{ id: "p1", code: "PRJ-2026-0001", name: "PLC Rack" }], total: 1, page: 1, page_size: 50 }),
        "POST /inventory/reservations": ({ body }) => {
          reserved = body;
          return {};
        },
        "PATCH /parts/pt1": ({ body }) => {
          minimum = body;
          return {};
        },
        "GET /inventory/ledger": () => ({
          total: 1,
          items: [{ id: 7, created_at: "2026-11-05T05:00:00Z", part_id: "pt1", mpn: "RC0603FR-0710KL", location_code: "STORES", qty_delta: "300", reason: "GRN", ref_type: "grn_line", ref_id: "x", ref_label: null, lot_code: "L1", project_code: "PRJ-2026-0001", note: null, user_name: "Store Keeper" }],
        }),
        "GET /inventory/reservations": () => [
          { id: "r1", part_id: "pt1", mpn: "RC0603FR-0710KL", project_id: "p1", project_code: "PRJ-2026-0001", location_code: "STORES", qty: "100", status: "active", note: null, created_at: "2026-11-05T05:00:00Z", row_version: 2 },
        ],
        "POST /inventory/reservations/r1/release": ({ body }) => {
          released = body;
          return {};
        },
      }),
    );
    renderAt("/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Reserve RC0603FR-0710KL" }));
    const dialog = await screen.findByRole("dialog", { name: "Reserve RC0603FR-0710KL" }, { timeout: 5000 });
    await userEvent.click(within(dialog).getByRole("combobox", { name: /Project/ }));
    await userEvent.click(await screen.findByRole("option", { name: /PRJ-2026-0001/ }));
    await userEvent.type(within(dialog).getByLabelText(/Quantity/), "100");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reserve" }));
    await waitFor(() => expect(reserved).toEqual({ part_id: "pt1", project_id: "p1", qty: "100", location_id: null, note: null }));

    await userEvent.click(screen.getByRole("button", { name: "Minimum stock for RC0603FR-0710KL" }));
    const minDialog = await screen.findByRole("dialog", { name: "Minimum stock for RC0603FR-0710KL" }, { timeout: 5000 });
    await userEvent.type(within(minDialog).getByLabelText(/Minimum stock/), "500");
    await userEvent.click(within(minDialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(minimum).toEqual({ row_version: 4, min_stock: 500, msl_level: null }));

    await userEvent.click(screen.getByRole("tab", { name: "Ledger" }));
    const ledgerRow = await screen.findByRole("row", { name: /Store Keeper/ });
    expect(within(ledgerRow).getByText("+300")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Reservations" }));
    await userEvent.click(await screen.findByRole("button", { name: "Release" }));
    await waitFor(() => expect(released).toEqual({ row_version: 2 }));
  });
});


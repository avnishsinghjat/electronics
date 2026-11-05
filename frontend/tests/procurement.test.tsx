import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { PendingLine, PurchaseOrderDetail, RequisitionDetail, Tracker, TrackerLine } from "@/features/procurement/api";
import type { ProjectTree } from "@/features/projects/api";

import { type Handler, makeMe, mockApi, renderAt, signedInRoutes } from "./utils";

const TREE: ProjectTree = {
  project: {
    id: "p1", division_id: "d1", code: "PRJ-2026-0001", name: "PLC Rack", client_name: "Sahyadri", client_po_ref: null,
    start_date: null, due_date: null, status: "active", project_manager_id: null, notes: null, is_sample: false, row_version: 1,
    created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", division_code: "IND", division_name: "Industrial",
    project_manager_name: null, module_count: 1,
  },
  modules: [{ id: "m1", project_id: "p1", code: "MOD-CPU", name: "CPU module", qty_to_deliver: 25, description: null, row_version: 1, assemblies: [] }],
};

function tline(l: Partial<TrackerLine>): TrackerLine {
  return {
    boq_line_id: "bl1", boq_id: "b1", boq_name: "CPU BOM", revision: "A", module_id: "m1", module_code: "MOD-CPU", line_no: 1,
    ref_des: "R1-R4", part_id: "pt1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", description: "Res 10k", category: "Passive",
    unit: "pcs", dnp: false, required_qty: "100", ordered_qty: "100.0000", received_qty: "60.0000", issued_qty: "0",
    shortfall: "0", pending_receipt: "40.0000", being_ordered: "0", status: "Partially received", vendors: ["Deccan Components"],
    purchase_orders: [{ po_id: "po1", po_number: "PO-2026-0007", vendor_name: "Deccan Components", expected_date: "2026-10-01", outstanding: "40.0000" }],
    expected_date: "2026-10-01", days_overdue: 35, value_pending: "4.80", ...l,
  };
}

const TRACKER: Tracker = {
  project_id: "p1", project_code: "PRJ-2026-0001", project_name: "PLC Rack",
  kpis: { lines: 3, lines_required: 2, pct_fully_received: 50, lines_to_order: 1, lines_awaiting_delivery: 1, overdue_lines: 1, value_pending: "4.80" },
  modules: [{ module_id: "m1", module_code: "MOD-CPU", module_name: "CPU module", lines: 2, lines_received: 1, clear_to_build: false, reason: "1 of 2 lines not fully received" }],
  lines: [
    tline({}),
    tline({ boq_line_id: "bl2", line_no: 2, mpn: "STM32F407VGT6", description: "MCU", category: "IC", required_qty: "25", ordered_qty: "0", received_qty: "0", shortfall: "25", pending_receipt: "0", status: "Not ordered", vendors: [], purchase_orders: [], expected_date: null, days_overdue: 0, value_pending: "0" }),
    tline({ boq_line_id: "bl3", line_no: 3, mpn: "MCP2551-I/SN", description: "CAN", category: "IC", required_qty: "25", ordered_qty: "25", received_qty: "25", shortfall: "0", pending_receipt: "0", status: "Received", vendors: ["Lakshmi Semi"], purchase_orders: [], expected_date: null, days_overdue: 0, value_pending: "0" }),
  ],
  unreleased_boqs: [],
};

function base(extra: Record<string, Handler> = {}) {
  return signedInRoutes(makeMe(), { "GET /divisions": () => [], "GET /projects/p1/tree": () => TREE, ...extra });
}

const PR: RequisitionDetail = {
  id: "pr1", number: "PR-2026-0003", project_id: "p1", project_code: "PRJ-2026-0001", project_name: "PLC Rack", status: "draft",
  submitted_at: null, approved_by_name: null, approved_at: null, decision_note: null, notes: null, created_at: "2026-11-05T05:00:00Z",
  created_by_name: "Priya PM", line_count: 1, purchase_orders: [], row_version: 1,
  lines: [{ id: "prl1", boq_line_id: "bl2", boq_ref: "CPU BOM rev A line 2", part_id: "pt2", mpn: "STM32F407VGT6", manufacturer: "ST", description: "MCU", unit: "pcs", qty: "25.0000", suggested_vendor_id: null, suggested_vendor_name: null, notes: null }],
};

const VENDORS = [{ id: "v1", code: "V-DC", name: "Deccan Components", gstin: null, address: null, city: "Pune", state: null, contacts: [], payment_terms: "30 days", lead_time_days: 7, rating: "4.0", notes: null, is_sample: false, open_po_count: 1, row_version: 1 }];

const PO: PurchaseOrderDetail = {
  id: "po1", number: "PO-2026-0007", vendor_id: "v1", vendor_code: "V-DC", vendor_name: "Deccan Components", requisition_id: null,
  requisition_number: null, status: "issued", order_date: "2026-10-20", issued_at: "2026-10-20T05:00:00Z", currency: "INR", notes: null,
  total: "12.00", line_count: 2, next_expected: "2026-11-20", project_codes: ["PRJ-2026-0001"], created_at: "2026-10-20T05:00:00Z", row_version: 3,
  receipts: [],
  lines: [
    { id: "pl1", line_no: 1, part_id: "pt1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", description: "Res 10k", unit: "pcs", msl_level: null, qty_ordered: "100.0000", unit_price: "0.1200", amount: "12.00", expected_date: "2026-11-20", is_cancelled: false, notes: null, qty_accepted: "0", qty_rejected: "0", qty_on_hold: "0", outstanding: "100.0000", allocations: [{ id: "a1", boq_line_id: "bl1", boq_ref: "CPU BOM rev A line 1", project_id: "p1", project_code: "PRJ-2026-0001", qty: "100.0000", received: "0" }], row_version: 1 },
    { id: "pl2", line_no: 2, part_id: "pt2", mpn: "STM32F407VGT6", manufacturer: "ST", description: "MCU", unit: "pcs", msl_level: 3, qty_ordered: "25.0000", unit_price: "780.0000", amount: "19500.00", expected_date: "2026-11-20", is_cancelled: false, notes: null, qty_accepted: "0", qty_rejected: "0", qty_on_hold: "0", outstanding: "25.0000", allocations: [], row_version: 1 },
  ],
};

const LOCATIONS = [
  { id: "loc-s", code: "STORES", name: "Main stores", kind: "stores", parent_id: null },
  { id: "loc-m", code: "MSL-DRY-1", name: "MSL dry cabinet", kind: "msl_cabinet", parent_id: null },
];

describe("Project tracker", () => {
  it("shows KPIs, clear-to-build, PO links, filters and grouping", async () => {
    mockApi(base({ "GET /projects/p1/tracker": () => TRACKER }));
    renderAt("/projects/p1?tab=procurement");
    const panel = await screen.findByRole("tabpanel", { name: "Procurement" });
    const kpis = await within(panel).findByLabelText("Tracker summary");
    expect(kpis).toHaveTextContent("50%");
    expect(kpis).toHaveTextContent("Overdue lines1");
    expect(within(panel).getByLabelText("Clear to build by module")).toHaveTextContent("not clear: 1 of 2 lines not fully received");
    const row = within(panel).getByRole("row", { name: /RC0603FR-0710KL/ });
    expect(within(row).getByRole("link", { name: "PO-2026-0007" })).toHaveAttribute("href", "/procurement/orders/po1");
    expect(within(row).getByText("35")).toBeInTheDocument();

    await userEvent.click(within(panel).getByLabelText("Overdue only"));
    expect(within(panel).queryByRole("row", { name: /STM32F407VGT6/ })).not.toBeInTheDocument();
    await userEvent.click(within(panel).getByLabelText("Overdue only"));

    await userEvent.click(within(panel).getByRole("combobox", { name: "Group by" }));
    await userEvent.click(await screen.findByRole("option", { name: "Vendor" }));
    expect(within(panel).getByRole("region", { name: "Group Deccan Components" })).toBeInTheDocument();
    expect(within(within(panel).getByRole("region", { name: "Group No vendor yet" })).getByText("STM32F407VGT6")).toBeInTheDocument();
  });

  it("raises a requisition for all shortfall and opens it", async () => {
    let body: unknown = null;
    mockApi(
      base({
        "GET /projects/p1/tracker": () => TRACKER,
        "POST /projects/p1/requisitions": ({ body: b }) => {
          body = b;
          return PR;
        },
        "GET /requisitions/pr1": () => PR,
        "GET /vendors": () => VENDORS,
      }),
    );
    const router = renderAt("/projects/p1?tab=procurement");
    const panel = await screen.findByRole("tabpanel", { name: "Procurement" });
    await userEvent.click(await within(panel).findByRole("button", { name: /Requisition all shortfall/ }));
    await waitFor(() => expect(body).toEqual({ boq_line_ids: [], notes: null }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/procurement/requisitions/pr1"));
    expect(await screen.findByText("Requisition PR-2026-0003 raised with 1 line")).toBeInTheDocument();
  });
});

describe("Requisition", () => {
  it("picks a vendor, saves, and rejection needs a reason", async () => {
    let saved: { lines: { suggested_vendor_id: string | null; qty: string }[] } | null = null;
    mockApi(
      base({
        "GET /requisitions/pr1": () => (saved ? { ...PR, row_version: 2, lines: [{ ...PR.lines[0]!, suggested_vendor_id: "v1", suggested_vendor_name: "Deccan Components" }] } : PR),
        "GET /vendors": () => VENDORS,
        "PUT /requisitions/pr1": ({ body }) => {
          saved = body as typeof saved;
          return PR;
        },
      }),
    );
    renderAt("/procurement/requisitions/pr1");
    expect(await screen.findByRole("heading", { level: 1, name: "Requisition PR-2026-0003" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("combobox", { name: "Vendor for STM32F407VGT6" }));
    await userEvent.click(await screen.findByRole("option", { name: "Deccan Components" }));
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeDisabled(); // unsaved changes
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved?.lines[0]).toMatchObject({ suggested_vendor_id: "v1", qty: "25" }));
  });

  it("approver must give a reason to reject", async () => {
    let decision: unknown = null;
    const submitted = { ...PR, status: "submitted" as const, row_version: 3 };
    mockApi(
      base({
        "GET /requisitions/pr1": () => submitted,
        "GET /vendors": () => VENDORS,
        "POST /requisitions/pr1/decision": ({ body }) => {
          decision = body;
          return { ...submitted, status: "rejected", decision_note: "Wait" };
        },
      }),
    );
    renderAt("/procurement/requisitions/pr1");
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog", { name: "Reject PR-2026-0003?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject" }));
    expect(await screen.findByText("Give a reason when rejecting")).toBeInTheDocument();
    expect(decision).toBeNull();
    await userEvent.type(within(dialog).getByLabelText(/Reason/), "Wait for client ECO");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(decision).toEqual({ row_version: 3, approve: false, note: "Wait for client ECO" }));
  });
});

describe("Purchase order and receiving", () => {
  it("receives goods: accepted = received − rejected − hold, MSL parts default to the dry cabinet", async () => {
    let posted: { lines: Record<string, unknown>[]; delivery_note_ref: string } | null = null;
    mockApi(
      base({
        "GET /purchase-orders/po1": () => PO,
        "GET /vendors": () => VENDORS,
        "GET /inventory/locations": () => LOCATIONS,
        "POST /goods-receipts": ({ body }) => {
          posted = body as typeof posted;
          return { id: "g1", number: "GRN-2026-0004", qty_accepted: "57", lines: [], returns: [] };
        },
        "GET /goods-receipts/g1": () => ({ id: "g1", number: "GRN-2026-0004", purchase_order_id: "po1", po_number: "PO-2026-0007", vendor_name: "Deccan Components", status: "posted", received_at: null, received_by_name: null, delivery_note_ref: null, coc_file_id: null, notes: null, qty_accepted: "57", qty_rejected: "3", qty_on_hold: "0", row_version: 1, lines: [], returns: [] }),
        "GET /files": () => [],
      }),
    );
    const router = renderAt("/procurement/orders/po1");
    await userEvent.click(await screen.findByRole("button", { name: "Receive goods" }));
    const dialog = await screen.findByRole("dialog", { name: "Receive goods on PO-2026-0007" });
    await waitFor(() => expect(within(dialog).getByRole("combobox", { name: "Location, line 2" })).toHaveTextContent("MSL-DRY-1"));
    expect(within(dialog).getByRole("combobox", { name: "Location, line 1" })).toHaveTextContent("STORES");
    await userEvent.type(within(dialog).getByLabelText("Received, line 1"), "60");
    await userEvent.type(within(dialog).getByLabelText("Rejected, line 1"), "3");
    expect(within(dialog).getByLabelText("Accepted, line 1")).toHaveTextContent("57");
    await userEvent.click(within(dialog).getByRole("button", { name: "Post goods receipt" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Line 1: give the reason for the rejection");
    await userEvent.type(within(dialog).getByLabelText("Rejection reason, line 1"), "Bent leads");
    await userEvent.type(within(dialog).getByLabelText("Vendor delivery note"), "DN-77");
    await userEvent.click(within(dialog).getByRole("button", { name: "Post goods receipt" }));
    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.delivery_note_ref).toBe("DN-77");
    expect(posted!.lines).toEqual([
      expect.objectContaining({ po_line_id: "pl1", location_id: "loc-s", qty_received: "60", qty_accepted: "57", qty_rejected: "3", qty_on_hold: "0", reject_reason: "Bent leads" }),
    ]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/procurement/receipts/g1"));
  });

  it("issues a draft order after confirmation", async () => {
    let issued: unknown = null;
    const draft = { ...PO, status: "draft" as const };
    mockApi(
      base({
        "GET /purchase-orders/po1": () => (issued ? PO : draft),
        "GET /vendors": () => VENDORS,
        "POST /purchase-orders/po1/issue": ({ body }) => {
          issued = body;
          return PO;
        },
      }),
    );
    renderAt("/procurement/orders/po1");
    await userEvent.click(await screen.findByRole("button", { name: "Issue to vendor" }));
    const dialog = await screen.findByRole("dialog", { name: "Issue PO-2026-0007 to Deccan Components?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Issue order" }));
    await waitFor(() => expect(issued).toEqual({ row_version: 3, note: null }));
    expect(await screen.findByText("PO-2026-0007 issued")).toBeInTheDocument();
  });
});

describe("Procurement page", () => {
  const PENDING: PendingLine[] = [
    { po_id: "po1", po_number: "PO-2026-0007", po_status: "issued", po_line_id: "pl1", line_no: 1, vendor_id: "v1", vendor_name: "Deccan Components", part_id: "pt1", mpn: "RC0603FR-0710KL", description: "Res", qty_ordered: "100", qty_received: "60", outstanding: "40", unit_price: "0.12", value_pending: "4.80", expected_date: "2026-10-01", days_overdue: 35, project_codes: ["PRJ-2026-0001"], row_version: 1 },
    { po_id: "po2", po_number: "PO-2026-0008", po_status: "issued", po_line_id: "pl9", line_no: 1, vendor_id: "v2", vendor_name: "Lakshmi Semi", part_id: "pt2", mpn: "STM32F407VGT6", description: "MCU", qty_ordered: "25", qty_received: "0", outstanding: "25", unit_price: "780", value_pending: "19500", expected_date: "2099-01-01", days_overdue: 0, project_codes: ["PRJ-2026-0001"], row_version: 1 },
  ];

  it("lists pending deliveries and updates a promised date", async () => {
    let patched: unknown = null;
    mockApi(
      base({
        "GET /procurement/pending": () => PENDING,
        "PATCH /po-lines/pl1": ({ body }) => {
          patched = body;
          return PO;
        },
      }),
    );
    renderAt("/procurement");
    expect(await screen.findByRole("heading", { level: 1, name: "Procurement" })).toBeInTheDocument();
    expect(await screen.findByText("1 overdue · ₹ 19,504.80 pending")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Overdue only"));
    expect(screen.queryByText("STM32F407VGT6")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Change expected date of PO-2026-0007 line 1" }));
    const dialog = await screen.findByRole("dialog", { name: "PO-2026-0007 line 1" });
    const date = within(dialog).getByLabelText("Expected delivery");
    await userEvent.clear(date);
    await userEvent.type(date, "20 Nov 2026{Enter}");
    await userEvent.type(within(dialog).getByLabelText("Follow-up note"), "Ships Friday");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patched).toEqual({ row_version: 1, expected_date: "2026-11-20", notes: "Ships Friday" }));
  });

  it("validates a new vendor's GSTIN before saving", async () => {
    let created: Record<string, unknown> | null = null;
    mockApi(
      base({
        "GET /procurement/pending": () => [],
        "GET /vendors": () => VENDORS,
        "POST /vendors": ({ body }) => {
          created = body as Record<string, unknown>;
          return { ...VENDORS[0], id: "v9", name: "New Co" };
        },
      }),
    );
    renderAt("/procurement?tab=vendors");
    expect(await screen.findByRole("button", { name: "Deccan Components" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New vendor" }));
    const drawer = await screen.findByRole("dialog", { name: "New vendor" });
    await userEvent.type(within(drawer).getByLabelText(/Code/), "v-new");
    await userEvent.type(within(drawer).getByLabelText(/^Name/), "New Co");
    await userEvent.type(within(drawer).getByLabelText(/GSTIN/), "27ABC");
    await userEvent.click(within(drawer).getByRole("button", { name: "Add vendor" }));
    expect(await within(drawer).findByText(/15 characters/)).toBeInTheDocument();
    expect(created).toBeNull();
    await userEvent.clear(within(drawer).getByLabelText(/GSTIN/));
    await userEvent.type(within(drawer).getByLabelText(/GSTIN/), "27aabcs1234f1z5");
    await userEvent.click(within(drawer).getByRole("button", { name: "Add contact" }));
    await userEvent.type(within(drawer).getByLabelText("Contact 1 name"), "Ravi");
    await userEvent.click(within(drawer).getByRole("button", { name: "Add vendor" }));
    await waitFor(() => expect(created).toMatchObject({ code: "V-NEW", gstin: "27AABCS1234F1Z5", contacts: [{ name: "Ravi", role: null, phone: null, email: null }] }));
  });
});

describe("PO editor", () => {
  it("checks lines before creating a draft", { timeout: 20_000 }, async () => {
    let created: Record<string, unknown> | null = null;
    mockApi(
      base({
        "GET /procurement/pending": () => [],
        "GET /vendors": () => VENDORS,
        "GET /parts": () => [{ id: "pt1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", description: "Res", package: "0603", value: "10k", category: "Passive", unit: "pcs" }],
        "POST /purchase-orders": ({ body }) => {
          created = body as Record<string, unknown>;
          return { ...PO, id: "po9", number: "PO-2026-0009", status: "draft" };
        },
        "GET /purchase-orders/po9": () => ({ ...PO, id: "po9", number: "PO-2026-0009", status: "draft" }),
      }),
    );
    const router = renderAt("/procurement");
    await userEvent.click(await screen.findByRole("button", { name: "New purchase order" }));
    const drawer = await screen.findByRole("dialog", { name: "New purchase order" });
    await userEvent.click(within(drawer).getByRole("button", { name: "Create draft" }));
    expect(within(drawer).getByRole("alert")).toHaveTextContent("Choose the vendor");
    await userEvent.click(within(drawer).getByRole("combobox", { name: /Vendor/ }));
    await userEvent.click(await screen.findByRole("option", { name: /Deccan Components/ }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Create draft" }));
    expect(within(drawer).getByRole("alert")).toHaveTextContent("Line 1: choose the part");
    await userEvent.click(within(drawer).getByRole("combobox", { name: /Part/ }));
    const searches = await screen.findAllByPlaceholderText("Search…");
    await userEvent.type(searches[searches.length - 1]!, "RC06");
    await userEvent.click(await screen.findByRole("option", { name: /RC0603FR-0710KL/ }));
    await userEvent.type(within(drawer).getByLabelText(/Quantity/), "4000");
    await userEvent.type(within(drawer).getByLabelText(/Unit price/), "0.12");
    expect(within(drawer).getByText("₹ 480.00")).toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "Create draft" }));
    await waitFor(() => expect(created).toMatchObject({ vendor_id: "v1", lines: [{ part_id: "pt1", qty_ordered: "4000", unit_price: "0.12", allocations: [] }] }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/procurement/orders/po9"));
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { BoardColumn, Kit, ScanResult, StageTemplate, Unit, WorkOrderDetail } from "@/features/production/api";

import { type Handler, makeMe, mockApi, renderAt, signedInRoutes } from "./utils";

function base(extra: Record<string, Handler> = {}) {
  return signedInRoutes(makeMe(), { "GET /divisions": () => [], ...extra });
}

const STAGES = [
  { id: "s1", seq: 1, stage_code: "kitting", name: "Kitting", requires_qc: false, status: "completed", units_in: 2, units_done: 2, units_failed: 0, units_awaiting_qc: 0 },
  { id: "s2", seq: 2, stage_code: "reflow", name: "Reflow", requires_qc: true, status: "in_progress", units_in: 2, units_done: 0, units_failed: 0, units_awaiting_qc: 0 },
  { id: "s3", seq: 3, stage_code: "packing", name: "Packing", requires_qc: false, status: "not_started", units_in: 0, units_done: 0, units_failed: 0, units_awaiting_qc: 0 },
] as WorkOrderDetail["stages"];

function wo(w: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return {
    id: "w1", number: "WO-2026-0004", project_id: "p1", project_code: "PRJ-2026-0001", project_name: "PLC Rack", module_id: "m1",
    module_code: "MOD-CPU", assembly_id: "a1", assembly_label: "CPU1 rev B · PLC CPU board", boq_id: "b1", build_qty: 2,
    status: "in_progress", planned_start: null, planned_end: "2026-12-01", released_at: "2026-11-05T05:00:00Z",
    release_override_reason: null, track_serials: true, notes: null, lot_id: "l1", lot_number: "LOT-2026-0004",
    current_stage: "Reflow", units_completed: 0, units_failed: 0, serial_count: 2, created_at: "2026-11-05T05:00:00Z",
    row_version: 3, stages: STAGES, readiness: null, ...w,
  };
}

const UNITS: Unit[] = [
  { id: "u1", serial_number: "FT-CPU1-2026-00001", status: "in_production", current_stage: "Reflow", current_stage_id: "s2", current_stage_status: "not_started" },
  { id: "u2", serial_number: "FT-CPU1-2026-00002", status: "in_production", current_stage: "Reflow", current_stage_id: "s2", current_stage_status: "in_progress" },
];

const KIT: Kit = {
  boq_id: "b1", boq_name: "CPU BOM", revision: "A", complete: false,
  lines: [
    { boq_line_id: "bl1", line_no: 1, ref_des: "R1-R4", part_id: "pt1", mpn: "RC0603FR-0710KL", description: "Res", unit: "pcs", dnp: false, required: "8", issued: "2", shortage: "6", available: "40", reserved_for_project: "8" },
    { boq_line_id: "bl2", line_no: 2, ref_des: "R9", part_id: "pt9", mpn: "DNP-PART", description: "Not fitted", unit: "pcs", dnp: true, required: "0", issued: "0", shortage: "0", available: "0", reserved_for_project: "0" },
  ],
};

describe("Production board and templates", () => {
  it("shows work orders by stage and edits a stage template", async () => {
    const board: BoardColumn[] = [
      { key: "draft", label: "Planned", cards: [{ work_order_id: "w9", number: "WO-2026-0009", project_code: "PRJ-2026-0001", assembly_label: "CPU1 rev B", build_qty: 20, status: "draft", stage_name: "Kitting", stage_seq: 1, stage_count: 3, units_at_stage: 0, units_done_at_stage: 0, awaiting_qc: 0, planned_end: null }] },
      { key: "released", label: "Released, not started", cards: [] },
      { key: "reflow", label: "Reflow", cards: [{ work_order_id: "w1", number: "WO-2026-0004", project_code: "PRJ-2026-0001", assembly_label: "CPU1 rev B", build_qty: 2, status: "in_progress", stage_name: "Reflow", stage_seq: 2, stage_count: 3, units_at_stage: 2, units_done_at_stage: 0, awaiting_qc: 1, planned_end: "2026-12-01" }] },
      { key: "aoi", label: "AOI", cards: [] },
      { key: "completed", label: "Completed", cards: [] },
    ];
    const tpl: StageTemplate = {
      id: "t2", name: "Quick", description: null, is_default: false, assembly_count: 1, row_version: 2,
      steps: [
        { id: "x1", seq: 1, stage_code: "smt", name: "SMT", requires_qc: false },
        { id: "x2", seq: 2, stage_code: "aoi", name: "AOI", requires_qc: false },
      ],
    };
    let saved: { steps: { name: string; requires_qc: boolean }[] } | null = null;
    mockApi(
      base({
        "GET /production/board": () => board,
        "GET /production/stage-templates": () => [tpl],
        "PUT /stage-templates/t2": ({ body }) => {
          saved = body as typeof saved;
          return tpl;
        },
      }),
    );
    renderAt("/production");
    const reflow = await screen.findByRole("region", { name: "Column Reflow" });
    expect(within(reflow).getByRole("link", { name: /WO-2026-0004/ })).toHaveAttribute("href", "/production/work-orders/w1");
    expect(within(reflow).getByText(/1 awaiting QC/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Column AOI" })).not.toBeInTheDocument(); // empty stage columns hidden

    await userEvent.click(screen.getByRole("tab", { name: "Stage templates" }));
    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit Quick" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Move stage 2 up" }));
    await userEvent.click(within(dialog).getByLabelText("Stage 1 requires QC"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Add stage" }));
    await userEvent.type(within(dialog).getByLabelText("Stage 3 name"), "Potting");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save template" }));
    await waitFor(() =>
      expect(saved?.steps.map((s) => [s.name, s.requires_qc])).toEqual([["AOI", true], ["SMT", false], ["Potting", false]]),
    );
  });
});

describe("Work order page", () => {
  it("draft not clear to build: a PM releases only with a reason", async () => {
    let released: unknown = null;
    const draft = wo({ status: "draft", current_stage: null, readiness: { clear_to_build: false, reason: "1 of 2 lines not fully received", lines: 2, lines_received: 1 } });
    mockApi(
      base({
        "GET /work-orders/w1": () => draft,
        "GET /work-orders/w1/units": () => [],
        "POST /work-orders/w1/release": ({ body }) => {
          released = body;
          return { ...draft, status: "released" };
        },
      }),
    );
    renderAt("/production/work-orders/w1");
    expect(await screen.findByText("Not clear to build: 1 of 2 lines not fully received.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Release to production" }));
    const dialog = await screen.findByRole("dialog", { name: "Release WO-2026-0004" });
    const go = within(dialog).getByRole("button", { name: "Release with override" });
    expect(go).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText(/Reason for releasing anyway/), "Client approved a pilot lot");
    await userEvent.click(go);
    await waitFor(() => expect(released).toEqual({ row_version: 3, override_reason: "Client approved a pilot lot" }));
  });

  it("unit actions: start a unit, pass at a QC stage sends it to QC", async () => {
    const calls: unknown[] = [];
    mockApi(
      base({
        "GET /work-orders/w1": () => wo(),
        "GET /work-orders/w1/units": () => UNITS,
        "POST /work-order-stages/s2/progress": ({ body }) => {
          calls.push(body);
          return { id: "p1", work_order_stage_id: "s2", stage_name: "Reflow", seq: 2, serial_unit_id: "u1", serial_number: "x", status: calls.length === 1 ? "in_progress" : "awaiting_qc", started_at: null, completed_at: null, qty_passed: 1, qty_failed: 0, operator_name: null, notes: null };
        },
      }),
    );
    renderAt("/production/work-orders/w1");
    const stepper = await screen.findByRole("list", { name: "Stages" });
    expect(within(stepper).getAllByRole("listitem")).toHaveLength(3);
    await userEvent.click(await screen.findByRole("button", { name: "Start stage for FT-CPU1-2026-00001" }));
    await userEvent.click(screen.getByRole("button", { name: "Pass FT-CPU1-2026-00002" }));
    await waitFor(() => expect(calls).toEqual([
      { action: "start", serial_unit_id: "u1", passed: null },
      { action: "finish", serial_unit_id: "u2", passed: true },
    ]));
    expect(await screen.findByText("FT-CPU1-2026-00002: waiting for QC")).toBeInTheDocument();
  });

  it("kitting suggests the oldest lots up to the shortage", async () => {
    let issued: { issues: unknown[] } | null = null;
    mockApi(
      base({
        "GET /work-orders/w1": () => wo(),
        "GET /work-orders/w1/units": () => UNITS,
        "GET /work-orders/w1/kit": () => KIT,
        "GET /work-orders/w1/kit/records": () => [],
        "GET /inventory/lots": () => [
          { location_id: "loc-s", location_code: "STORES", lot_code: "L1", qty: "4" },
          { location_id: "loc-s", location_code: "STORES", lot_code: "L2", qty: "10" },
        ],
        "POST /work-orders/w1/kit/issue": ({ body }) => {
          issued = body as typeof issued;
          return [];
        },
      }),
    );
    renderAt("/production/work-orders/w1");
    await userEvent.click(await screen.findByRole("tab", { name: "Kitting" }));
    expect(await screen.findByText("1 line short")).toBeInTheDocument();
    expect(screen.queryByText("DNP-PART")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Issue" }));
    const dialog = await screen.findByRole("dialog", { name: "Issue RC0603FR-0710KL" });
    await waitFor(() => expect(within(dialog).getByLabelText("Issue from STORES lot L1")).toHaveValue("4"));
    expect(within(dialog).getByLabelText("Issue from STORES lot L2")).toHaveValue("2");
    await userEvent.click(within(dialog).getByRole("button", { name: "Issue" }));
    await waitFor(() =>
      expect(issued?.issues).toEqual([
        { boq_line_id: "bl1", location_id: "loc-s", qty: "4", lot_code: "L1", note: null },
        { boq_line_id: "bl1", location_id: "loc-s", qty: "2", lot_code: "L2", note: null },
      ]),
    );
  });

  it("lot-tracked orders record passed and failed quantities", async () => {
    let body: unknown = null;
    const lotWo = wo({
      track_serials: false,
      stages: [{ ...STAGES[0]!, status: "in_progress", units_done: 0, units_in: 10, requires_qc: false }, { ...STAGES[2]! }],
    });
    mockApi(
      base({
        "GET /work-orders/w1": () => lotWo,
        "POST /work-order-stages/s1/progress": ({ body: b }) => {
          body = b;
          return {};
        },
      }),
    );
    renderAt("/production/work-orders/w1");
    const stage = await screen.findByRole("listitem", { name: "Stage 1 Kitting" });
    const passed = within(stage).getByLabelText("Passed");
    await userEvent.clear(passed);
    await userEvent.type(passed, "9");
    const failed = within(stage).getByLabelText("Failed");
    await userEvent.clear(failed);
    await userEvent.type(failed, "1");
    await userEvent.click(within(stage).getByRole("button", { name: "Complete Kitting" }));
    await waitFor(() => expect(body).toEqual({ action: "complete", qty_passed: 9, qty_failed: 1, notes: null }));
  });
});

describe("Shop floor", () => {
  it("finds a unit by serial and offers the next action", async () => {
    let progressed: unknown = null;
    const scan: ScanResult = {
      serial_unit_id: "u1", serial_number: "FT-CPU1-2026-00001", work_order_id: "w1", work_order_number: "WO-2026-0004",
      unit_status: "in_production", stage: null, stage_id: "s2", stage_name: "Reflow", stage_requires_qc: true, next_action: "start",
    };
    mockApi(
      base({
        "GET /work-orders": () => [],
        "GET /production/scan": ({ path }) => (path.includes("NOPE") ? new Response(JSON.stringify({ error: { code: "serial_not_found", message: "No unit with serial NOPE", details: null } }), { status: 404, headers: { "Content-Type": "application/json" } }) : scan),
        "POST /work-order-stages/s2/progress": ({ body }) => {
          progressed = body;
          return { id: "p", work_order_stage_id: "s2", stage_name: "Reflow", seq: 2, serial_unit_id: "u1", serial_number: "FT-CPU1-2026-00001", status: "in_progress", started_at: null, completed_at: null, qty_passed: 0, qty_failed: 0, operator_name: null, notes: null };
        },
      }),
    );
    renderAt("/shop-floor");
    const input = await screen.findByLabelText("Serial number");
    await userEvent.type(input, "NOPE{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("No unit with serial NOPE");
    await userEvent.type(input, "ft-cpu1-2026-00001{Enter}");
    const card = await screen.findByRole("region", { name: "Unit FT-CPU1-2026-00001" });
    expect(card).toHaveTextContent("Reflow");
    expect(card).toHaveTextContent("QC required");
    await userEvent.click(within(card).getByRole("button", { name: "Start stage for FT-CPU1-2026-00001" }));
    await waitFor(() => expect(progressed).toEqual({ action: "start", serial_unit_id: "u1", passed: null }));
    await userEvent.click(screen.getByRole("button", { name: "Camera" }));
    expect(await screen.findByRole("dialog", { name: "Scan a serial label" })).toHaveTextContent("secure (HTTPS) connection");
  });
});

describe("New work order", () => {
  it("creates one from the project's Production tab", async () => {
    let created: Record<string, unknown> | null = null;
    const tree = {
      project: { id: "p1", division_id: "d1", code: "PRJ-2026-0001", name: "PLC Rack", client_name: "S", client_po_ref: null, start_date: null, due_date: null, status: "active", project_manager_id: null, notes: null, is_sample: false, row_version: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", division_code: "IND", division_name: "Industrial", project_manager_name: null, module_count: 1 },
      modules: [{ id: "m1", project_id: "p1", code: "MOD-CPU", name: "CPU", qty_to_deliver: 25, description: null, row_version: 1, assemblies: [{ id: "a1", module_id: "m1", code: "CPU1", board_name: "PLC CPU board", revision: "B", qty_per_module: 1, layer_count: 4, size_x_mm: null, size_y_mm: null, finish: null, kicad_project_file_id: null, assembly_drawing_file_id: null, stage_template_id: null, notes: null, row_version: 1 }] }],
    };
    mockApi(
      base({
        "GET /projects/p1/tree": () => tree,
        "GET /work-orders": () => [],
        "GET /projects/p1/boqs": () => [],
        "POST /work-orders": ({ body }) => {
          created = body as Record<string, unknown>;
          return wo({ id: "w7", number: "WO-2026-0007", status: "draft" });
        },
        "GET /work-orders/w7": () => wo({ id: "w7", number: "WO-2026-0007", status: "draft" }),
        "GET /work-orders/w7/units": () => [],
      }),
    );
    const router = renderAt("/projects/p1?tab=production");
    await userEvent.click(await screen.findByRole("button", { name: "New work order" }));
    const drawer = await screen.findByRole("dialog", { name: "New work order" });
    await userEvent.click(within(drawer).getByRole("combobox", { name: /PCB assembly/ }));
    await userEvent.click(await screen.findByRole("option", { name: /PLC CPU board/ }));
    expect(within(drawer).getByLabelText(/Build quantity/)).toHaveValue("25"); // module quantity
    await userEvent.click(within(drawer).getByLabelText(/Track each board/));
    await userEvent.click(within(drawer).getByRole("button", { name: "Create work order" }));
    await waitFor(() => expect(created).toMatchObject({ assembly_id: "a1", build_qty: 25, track_serials: false, boq_id: null }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/production/work-orders/w7"));
  });
});

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { emptyRow, parseClipboard, rowsFromLines, rowsToInput } from "@/features/boq/BoqGrid";
import type { Boq, BoqLine, Comparison, ImportSession, RevisionDetail, RevisionSummary } from "@/features/boq/api";
import type { ProjectTree } from "@/features/projects/api";

import { type Handler, makeMe, mockApi, renderAt, signedInRoutes } from "./utils";

const TREE: ProjectTree = {
  project: {
    id: "p1", division_id: "d1", code: "PRJ-2026-0001", name: "PLC Rack", client_name: "Sahyadri", client_po_ref: null,
    start_date: null, due_date: null, status: "active", project_manager_id: null, notes: null, is_sample: false,
    row_version: 1, created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", division_code: "IND",
    division_name: "Industrial", project_manager_name: null, module_count: 1,
  },
  modules: [{ id: "m1", project_id: "p1", code: "MOD-CPU", name: "CPU module", qty_to_deliver: 25, description: null, row_version: 1, assemblies: [] }],
};

function rev(r: Partial<RevisionSummary>): RevisionSummary {
  return { id: "rA", revision: "A", status: "released", build_qty: 25, line_count: 2, released_at: "2026-10-01T00:00:00Z", created_at: "2026-10-01T00:00:00Z", row_version: 2, ...r };
}

function boq(revisions: RevisionSummary[]): Boq {
  return {
    id: "b1", project_id: "p1", project_code: "PRJ-2026-0001", project_name: "PLC Rack", module_id: "m1", module_code: "MOD-CPU",
    assembly_id: null, assembly_label: null, name: "Controller BOM", notes: null, row_version: 1, revisions,
  };
}

function line(l: Partial<BoqLine>): BoqLine {
  return {
    id: "l1", line_key: "k1", line_no: 1, part_id: "pt1", ref_des: "R1-R4", qty_per_unit: "4.0000", mpn: "RC0603FR-0710KL",
    manufacturer: "Yageo", description: "10k 0603", value: "10k", package: "0603", category: "Passive", unit: "pcs", dnp: false,
    attrition_pct: "5.00", attrition_override: false, unit_price: "0.12", preferred_vendor_id: null, notes: null,
    required_qty: "105", ordered_qty: "0", received_qty: "0", issued_qty: "0", shortfall: "105", pending_receipt: "0",
    status: "Not ordered", ...l,
  };
}

const LINES = [
  line({}),
  line({ id: "l2", line_key: "k2", line_no: 2, ref_des: "U1", qty_per_unit: "1.0000", mpn: "STM32F103C8T6", manufacturer: "ST", description: "MCU", category: "IC", attrition_pct: "2.00", required_qty: "26", shortfall: "26" }),
];

function detail(d: Partial<RevisionDetail>): RevisionDetail {
  return { id: "rA", boq_id: "b1", revision: "A", status: "released", build_qty: 25, attrition_by_category: { Passive: 5, IC: 2 }, released_at: "2026-10-01T00:00:00Z", notes: null, row_version: 2, lines: LINES, ...d };
}

function base(extra: Record<string, Handler> = {}) {
  return signedInRoutes(makeMe(), {
    "GET /divisions": () => [],
    "GET /projects/p1/tree": () => TREE,
    "GET /boq-import-fields": () => [
      { field: "ref_des", label: "Ref des" },
      { field: "qty", label: "Qty per unit" },
      { field: "mpn", label: "MPN" },
      { field: "manufacturer", label: "Manufacturer" },
      { field: "description", label: "Description" },
    ],
    "GET /boq-mapping-templates": () => [],
    ...extra,
  });
}

async function openBoqTab() {
  renderAt("/projects/p1?tab=boq");
  return screen.findByRole("tabpanel", { name: "BOQ" });
}

describe("BOQ grid helpers", () => {
  it("parses Excel clipboard text into rows and cells", () => {
    expect(parseClipboard("R1\t2\tABC\r\nR2\t3\tDEF\r\n")).toEqual([["R1", "2", "ABC"], ["R2", "3", "DEF"]]);
  });

  it("round-trips server lines and drops blank rows", () => {
    const rows = rowsFromLines(LINES);
    expect(rows[0]?.values.qty_per_unit).toBe("4");
    expect(rows[0]?.values.attrition_pct).toBe(""); // category default, not an override
    const input = rowsToInput([...rows, emptyRow()]);
    expect(input).toHaveLength(2);
    expect(input[0]).toMatchObject({ line_key: "k1", part_id: "pt1", ref_des: "R1-R4", qty_per_unit: "4", mpn: "RC0603FR-0710KL", attrition_pct: null, unit_price: "0.12", dnp: false });
  });

  it("reads DNP flags and per-line attrition overrides", () => {
    const row = emptyRow();
    row.values = { ...row.values, mpn: "X1", qty_per_unit: "", dnp: "yes", attrition_pct: "10" };
    expect(rowsToInput([row])[0]).toMatchObject({ qty_per_unit: "0", dnp: true, attrition_pct: "10", unit: "pcs", line_key: null });
  });
});

describe("BOQ tab", () => {
  it("offers to create a BOQ when the project has none", async () => {
    let body: unknown = null;
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [],
        "POST /projects/p1/boqs": ({ body: b }) => {
          body = b;
          return boq([rev({ id: "rA", status: "draft", line_count: 0, released_at: null })]);
        },
      }),
    );
    const panel = await openBoqTab();
    expect(await within(panel).findByText("No BOQ for this project yet")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "New BOQ" }));
    const dialog = await screen.findByRole("dialog", { name: "New BOQ" });
    await userEvent.type(within(dialog).getByLabelText(/Name/), "Controller BOM");
    await userEvent.click(within(dialog).getByRole("button", { name: "Start empty" }));
    await waitFor(() => expect(body).toEqual({ name: "Controller BOM", module_id: null, assembly_id: null, build_qty: null, create_revision: true }));
    expect(await screen.findByText("BOQ “Controller BOM” created")).toBeInTheDocument();
  });

  it("shows a released revision read-only with server-computed status", async () => {
    mockApi(base({ "GET /projects/p1/boqs": () => [boq([rev({})])], "GET /boq-revisions/rA": () => detail({}) }));
    const panel = await openBoqTab();
    expect(await within(panel).findByText("Read-only: start a new revision to change it")).toBeInTheDocument();
    const r1 = within(panel).getByRole("row", { name: /RC0603FR-0710KL/ });
    expect(within(r1).getAllByText("105")).toHaveLength(2); // required and still to order
    expect(within(r1).getByText("Not ordered")).toBeInTheDocument();
    expect(within(panel).queryByRole("grid", { name: "BOQ lines editor" })).not.toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "New revision" })).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: /Release revision/ })).not.toBeInTheDocument();
  });

  it("edits a draft in the grid: type, paste rows from Excel, keyboard navigation, save", async () => {
    let saved: { row_version: number; lines: Record<string, unknown>[] } | null = null;
    const draft = detail({ id: "rB", revision: "B", status: "draft", released_at: null, row_version: 4 });
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({ status: "superseded" }), rev({ id: "rB", revision: "B", status: "draft", released_at: null, row_version: 4 })])],
        "GET /boq-revisions/rB": () => draft,
        "GET /parts": () => [],
        "PUT /boq-revisions/rB/lines": ({ body }) => {
          saved = body as typeof saved;
          return rev({ id: "rB", revision: "B", status: "draft", line_count: 4, row_version: 5 });
        },
      }),
    );
    const panel = await openBoqTab();
    const grid = await within(panel).findByRole("grid", { name: "BOQ lines editor" });
    const save = within(panel).getByRole("button", { name: "Save lines" });
    expect(save).toBeDisabled();
    expect(within(panel).getByRole("button", { name: /Release revision/ })).toBeEnabled();

    // Change a quantity, then Enter moves down; Enter on the last row adds a row.
    const qty1 = within(grid).getByLabelText("Qty / unit, line 1");
    await userEvent.clear(qty1);
    await userEvent.type(qty1, "6{Enter}");
    expect(within(grid).getByLabelText("Qty / unit, line 2")).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(within(grid).getByLabelText("Qty / unit, line 3")).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}");
    expect(within(grid).getByLabelText("Qty / unit, line 2")).toHaveFocus();

    // Paste two rows (ref des, qty, MPN) starting in line 3's Ref des cell.
    const ref3 = within(grid).getByLabelText("Ref des, line 3");
    fireEvent.paste(ref3, { clipboardData: { getData: () => "C1,C2\t2\tGRM188R71C104KA01D\nJ1\t1\tB2B-XH-A\n" } });
    expect(await screen.findByText("Pasted 2 rows")).toBeInTheDocument();
    expect(within(grid).getByLabelText("MPN, line 4")).toHaveValue("B2B-XH-A");
    expect(save).toBeEnabled();
    expect(within(panel).getByRole("button", { name: /Release revision/ })).toBeDisabled();

    await userEvent.click(save);
    await waitFor(() => expect(saved).not.toBeNull());
    expect(saved!.row_version).toBe(4);
    expect(saved!.lines.map((l) => [l.ref_des, l.qty_per_unit, l.mpn, l.line_key])).toEqual([
      ["R1-R4", "6", "RC0603FR-0710KL", "k1"],
      ["U1", "1", "STM32F103C8T6", "k2"],
      ["C1,C2", "2", "GRM188R71C104KA01D", null],
      ["J1", "1", "B2B-XH-A", null],
    ]);
    expect(await screen.findByText("BOQ lines saved")).toBeInTheDocument();
  });

  it("suggests parts from the master as you type an MPN and links the picked part", async () => {
    let saved: { lines: Record<string, unknown>[] } | null = null;
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({ id: "rB", revision: "B", status: "draft", released_at: null })])],
        "GET /boq-revisions/rB": () => detail({ id: "rB", revision: "B", status: "draft", lines: [] }),
        "GET /parts": () => [{ id: "pt9", mpn: "LM358DR", manufacturer: "TI", description: "Dual op-amp", package: "SOIC-8", value: null, category: "IC", unit: "pcs" }],
        "PUT /boq-revisions/rB/lines": ({ body }) => {
          saved = body as typeof saved;
          return rev({ id: "rB", revision: "B", status: "draft" });
        },
      }),
    );
    const panel = await openBoqTab();
    await userEvent.click(await within(panel).findByRole("button", { name: "Add row" }));
    const grid = within(panel).getByRole("grid", { name: "BOQ lines editor" });
    await userEvent.type(within(grid).getByLabelText("Qty / unit, line 1"), "2");
    await userEvent.type(within(grid).getByLabelText("MPN, line 1"), "lm35");
    const list = await screen.findByRole("listbox", { name: "Matching parts" });
    expect(within(list).getByText(/Create part “lm35”/)).toBeInTheDocument();
    fireEvent.mouseDown(within(list).getByText("LM358DR"));
    expect(within(grid).getByLabelText("MPN, line 1")).toHaveValue("LM358DR");
    expect(within(grid).getByLabelText("Description, line 1")).toHaveValue("Dual op-amp");
    await userEvent.click(within(panel).getByRole("button", { name: "Save lines" }));
    await waitFor(() => expect(saved?.lines[0]).toMatchObject({ part_id: "pt9", mpn: "LM358DR", manufacturer: "TI", category: "IC", qty_per_unit: "2" }));
  });

  it("highlights the lines the server rejected", async () => {
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({ id: "rB", revision: "B", status: "draft", released_at: null })])],
        "GET /boq-revisions/rB": () => detail({ id: "rB", revision: "B", status: "draft" }),
        "PUT /boq-revisions/rB/lines": () =>
          new Response(JSON.stringify({ error: { code: "invalid_lines", message: "1 line has a problem", details: [{ line: 2, message: "Quantity must not be negative" }] } }), { status: 422, headers: { "Content-Type": "application/json" } }),
      }),
    );
    const panel = await openBoqTab();
    const grid = await within(panel).findByRole("grid", { name: "BOQ lines editor" });
    const qty = within(grid).getByLabelText("Qty / unit, line 2");
    await userEvent.clear(qty);
    await userEvent.type(qty, "-1");
    await userEvent.click(within(panel).getByRole("button", { name: "Save lines" }));
    expect(await within(panel).findByText("Line 2: Quantity must not be negative")).toBeInTheDocument();
  });

  it("releases a draft revision", async () => {
    let body: unknown = null;
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({ id: "rB", revision: "B", status: "draft", released_at: null, row_version: 7 })])],
        "GET /boq-revisions/rB": () => detail({ id: "rB", revision: "B", status: "draft", row_version: 7 }),
        "POST /boq-revisions/rB/release": ({ body: b }) => {
          body = b;
          return rev({ id: "rB", revision: "B", status: "released", row_version: 8 });
        },
      }),
    );
    const panel = await openBoqTab();
    await userEvent.click(await within(panel).findByRole("button", { name: /Release revision/ }));
    await waitFor(() => expect(body).toEqual({ row_version: 7 }));
    expect(await screen.findByText("Revision B released")).toBeInTheDocument();
  });

  it("compares two revisions and lists only the changes by default", async () => {
    const cmp: Comparison = {
      boq_id: "b1", from_revision: "A", to_revision: "B",
      summary: { added: 1, removed: 1, qty_changed: 1, substituted: 0, changed: 0, unchanged: 1 },
      lines: [
        { line_key: "k1", change: "qty_changed", from_line: { ref_des: "R1-R4", mpn: "RC0603FR-0710KL", qty_per_unit: "4" }, to_line: { ref_des: "R1-R6", mpn: "RC0603FR-0710KL", qty_per_unit: "6" }, changed_fields: ["ref_des", "qty_per_unit"] },
        { line_key: "k2", change: "unchanged", from_line: { mpn: "STM32F103C8T6", qty_per_unit: "1" }, to_line: { mpn: "STM32F103C8T6", qty_per_unit: "1" }, changed_fields: [] },
        { line_key: "k3", change: "removed", from_line: { mpn: "OLD-PART", qty_per_unit: "1" }, to_line: null, changed_fields: [] },
        { line_key: "k4", change: "added", from_line: null, to_line: { mpn: "NEW-PART", qty_per_unit: "2" }, changed_fields: [] },
      ],
    };
    const { calls } = mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({ status: "superseded" }), rev({ id: "rB", revision: "B" })])],
        "GET /boq-revisions/rB": () => detail({ id: "rB", revision: "B" }),
        "GET /boqs/b1/compare": () => cmp,
      }),
    );
    const panel = await openBoqTab();
    expect(await within(panel).findByRole("tab", { name: /Rev B/ })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(await within(panel).findByRole("button", { name: "Compare" }));
    const dialog = await screen.findByRole("dialog", { name: "Compare revisions of Controller BOM" });
    const summary = await within(dialog).findByLabelText("Change summary");
    expect(within(summary).getByText("Qty changed:").parentElement).toHaveTextContent("Qty changed: 1");
    expect(calls.some((c) => c.path === "/boqs/b1/compare?from=A&to=B")).toBe(true);
    expect(within(dialog).getByText("NEW-PART")).toBeInTheDocument();
    expect(within(dialog).getByText("OLD-PART")).toBeInTheDocument();
    expect(within(dialog).getByText("ref_des, qty_per_unit")).toBeInTheDocument();
    expect(within(dialog).queryByText("STM32F103C8T6")).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Show unchanged lines too" }));
    expect(within(dialog).getAllByText("STM32F103C8T6").length).toBeGreaterThan(0);
  });
});

describe("Import wizard", () => {
  const PARSED: ImportSession = {
    id: "i1", boq_id: "b1", file_id: "f1", file_name: "client-bom.csv", status: "parsed", encoding: "windows-1252", delimiter: ",",
    sheet: null, header_row: 1, headers: ["Designator", "Qty", "Part No", "Make", "Desc"],
    preview_rows: [["Sahyadri BOM rev 3", "", "", "", ""], ["Designator", "Qty", "Part No", "Make", "Desc"], ["R1-R4", "4", "RC0603FR-0710KL", "Yageo", "10k"], ["U1", "x", "", "ST", "MCU"]],
    total_rows: 4, mapping: { ref_des: 0, qty: 1, manufacturer: 3, description: 4 }, suggested_template_id: null, result: null,
    error: null, revision_id: null, row_version: 1,
  };

  it("uploads, fixes the mapping, shows blocking errors, then commits a clean file", async () => {
    let session: ImportSession = { ...PARSED, status: "uploaded" };
    let mappingBody: Record<string, unknown> | null = null;
    let commitBody: unknown = null;
    const withErrors = {
      lines: [], source_rows: 2,
      stats: { source_rows: 2, lines: 1, errors: 2, warnings: 1, unknown_parts: 1 },
      issues: [
        { row: 4, field: "qty", code: "invalid_qty", message: "Quantity “x” is not a number", severity: "error" as const },
        { row: 4, field: "mpn", code: "missing_mpn", message: "No MPN", severity: "error" as const },
        { row: 3, field: "mpn", code: "unknown_part", message: "RC0603FR-0710KL is not in the part master yet", severity: "warning" as const },
      ],
    };
    const clean = { lines: [], source_rows: 2, stats: { source_rows: 2, lines: 2, errors: 0, warnings: 0, unknown_parts: 0 }, issues: [] };
    let gets = 0;
    let validations = 0;
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({})])],
        "GET /boq-revisions/rA": () => detail({}),
        "POST /boqs/b1/imports": () => session,
        "GET /boq-imports/i1": () => {
          gets += 1;
          if (session.status === "uploaded" && gets > 1) session = { ...PARSED };
          return session;
        },
        "PUT /boq-imports/i1/mapping": ({ body }) => {
          mappingBody = body as Record<string, unknown>;
          validations += 1;
          session = { ...session, status: "validated", mapping: mappingBody.mapping as Record<string, number>, result: validations > 1 ? clean : withErrors, row_version: session.row_version + 1 };
          return session;
        },
        "POST /boq-imports/i1/commit": ({ body }) => {
          commitBody = body;
          return rev({ id: "rB", revision: "B", status: "released", line_count: 2 });
        },
        "GET /boq-revisions/rB": () => detail({ id: "rB", revision: "B" }),
      }),
    );
    const panel = await openBoqTab();
    await userEvent.click(await within(panel).findByRole("button", { name: "Import file" }));
    const dialog = await screen.findByRole("dialog", { name: "Import BOQ" });
    await userEvent.upload(dialog.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "client-bom.csv", { type: "text/csv" }));

    // Parsed: the mapping step shows detection results and the suggested mapping.
    const mapping = await within(dialog).findByRole("table", { name: "Column mapping" }, { timeout: 4000 });
    expect(within(dialog).getByText("Encoding windows-1252")).toBeInTheDocument();
    expect(await within(mapping).findByRole("combobox", { name: "Column for MPN" })).toHaveTextContent("— not in file —");
    await userEvent.click(within(mapping).getByRole("combobox", { name: "Column for MPN" }));
    await userEvent.click(await screen.findByRole("option", { name: "C: Part No" }));
    expect(within(mapping).getByText("RC0603FR-0710KL")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Validate file" }));
    await waitFor(() => expect(mappingBody).toMatchObject({ header_row: 1, mapping: { ref_des: 0, qty: 1, mpn: 2, manufacturer: 3, description: 4 }, decimal_comma: false, save_template_name: null, template_client: "Sahyadri" }));

    // Review: errors block the commit.
    expect(await within(dialog).findByText(/2 errors must be fixed/)).toBeInTheDocument();
    expect(within(dialog).getByText("Quantity “x” is not a number")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Commit as new revision" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Error report CSV" })).toBeInTheDocument();

    // Back to mapping, validate again; this time the file is clean.
    await userEvent.click(within(dialog).getByRole("button", { name: "Change mapping" }));
    await userEvent.click(await within(dialog).findByRole("button", { name: "Validate file" }));
    expect(await within(dialog).findByText(/No errors\. Committing creates a new BOQ revision/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByLabelText("Release the revision immediately"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Commit as new revision" }));
    await waitFor(() => expect(commitBody).toEqual({ row_version: 3, release: true, build_qty: null }));
    expect(await screen.findByText("Revision B created with 2 lines")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Import BOQ" })).not.toBeInTheDocument());
  });

  it("explains a file that could not be read", async () => {
    mockApi(
      base({
        "GET /projects/p1/boqs": () => [boq([rev({})])],
        "GET /boq-revisions/rA": () => detail({}),
        "POST /boqs/b1/imports": () => ({ ...PARSED, status: "failed", error: "The file is empty or is not a table" }),
        "GET /boq-imports/i1": () => ({ ...PARSED, status: "failed", error: "The file is empty or is not a table" }),
      }),
    );
    const panel = await openBoqTab();
    await userEvent.click(await within(panel).findByRole("button", { name: "Import file" }));
    const dialog = await screen.findByRole("dialog", { name: "Import BOQ" });
    await userEvent.upload(dialog.querySelector('input[type="file"]') as HTMLInputElement, new File([""], "empty.csv", { type: "text/csv" }));
    expect(await within(dialog).findByText("The file is empty or is not a table")).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Choose another file" }));
    expect(within(dialog).getByText("Drop the BOQ file here or browse")).toBeInTheDocument();
  });
});

describe("BOQ list page", () => {
  it("lists every BOQ with its current revision and links to the project tab", async () => {
    mockApi(base({ "GET /boqs": () => [boq([rev({ status: "superseded" }), rev({ id: "rB", revision: "B", status: "released", line_count: 42 })])] }));
    renderAt("/boq");
    expect(await screen.findByRole("heading", { level: 1, name: "Bills of quantity" })).toBeInTheDocument();
    const row = await screen.findByRole("row", { name: /Controller BOM/ });
    expect(within(row).getByRole("link", { name: "PRJ-2026-0001" })).toHaveAttribute("href", "/projects/p1?tab=boq");
    expect(within(row).getByText("B")).toBeInTheDocument();
    expect(within(row).getByText("released")).toBeInTheDocument();
    expect(within(row).getByText("42")).toBeInTheDocument();
  });
});

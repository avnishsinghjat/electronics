import type { ColumnDef } from "@tanstack/react-table";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { strFromU8, unzipSync } from "fflate";
import * as React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DataTable } from "@/design/components";
import { toCsv } from "@/design/components/data-table/export";

import { renderUi } from "../utils";

interface Line {
  id: string;
  mpn: string;
  manufacturer: string;
  qty: number;
}

const ROWS: Line[] = [
  { id: "1", mpn: "RC0603FR-0710KL", manufacturer: "Yageo", qty: 300 },
  { id: "2", mpn: "GRM188R71H104KA93D", manufacturer: "Murata", qty: 1200 },
  { id: "3", mpn: "STM32F407VGT6", manufacturer: "STMicroelectronics", qty: 25 },
  { id: "4", mpn: "BSS138", manufacturer: "onsemi, Inc.", qty: 50 },
];

const COLUMNS: ColumnDef<Line, unknown>[] = [
  { accessorKey: "mpn", header: "MPN", meta: { mono: true } },
  { accessorKey: "manufacturer", header: "Manufacturer" },
  { accessorKey: "qty", header: "Qty", meta: { align: "right", exportType: "number" } },
];

function bodyRows() {
  const table = screen.getByRole("table");
  return within(table)
    .getAllByRole("row")
    .filter((r) => r.closest("tbody") && !r.hasAttribute("data-virtual-spacer"));
}

function firstColumn() {
  return bodyRows().map((r) => within(r).getAllByRole("cell")[0]?.textContent);
}

let blobs: Blob[] = [];
beforeEach(() => {
  blobs = [];
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn((b: Blob) => {
      blobs.push(b);
      return "blob:test";
    }),
    revokeObjectURL: vi.fn(),
  }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});

describe("DataTable", () => {
  it("renders rows with mono and right-aligned cells", () => {
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} />);
    expect(firstColumn()).toEqual(["RC0603FR-0710KL", "GRM188R71H104KA93D", "STM32F407VGT6", "BSS138"]);
    const cells = within(bodyRows()[0] as HTMLElement).getAllByRole("cell");
    expect(cells[0]?.className).toContain("font-mono");
    expect(cells[2]?.className).toContain("text-right");
    expect(screen.getByText("4 of 4 rows")).toBeInTheDocument();
  });

  it("sorts ascending then descending on header click", async () => {
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} />);
    const qtyHeader = screen.getByRole("columnheader", { name: /Qty/ });
    await userEvent.click(within(qtyHeader).getByRole("button"));
    expect(qtyHeader).toHaveAttribute("aria-sort", "ascending");
    expect(bodyRows().map((r) => within(r).getAllByRole("cell")[2]?.textContent)).toEqual(["25", "50", "300", "1200"]);
    await userEvent.click(within(qtyHeader).getByRole("button"));
    expect(qtyHeader).toHaveAttribute("aria-sort", "descending");
    expect(firstColumn()[0]).toBe("GRM188R71H104KA93D");
  });

  it("filters by column and by global search", async () => {
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Filter Manufacturer" }), "mura");
    expect(firstColumn()).toEqual(["GRM188R71H104KA93D"]);
    expect(screen.getByText("1 of 4 rows")).toBeInTheDocument();
    await userEvent.clear(screen.getByRole("textbox", { name: "Filter Manufacturer" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Search table" }), "stm32");
    expect(firstColumn()).toEqual(["STM32F407VGT6"]);
    await userEvent.type(screen.getByRole("textbox", { name: "Search table" }), "zzz");
    expect(screen.getByText("No rows match the current filters.")).toBeInTheDocument();
  });

  it("selects rows and reports the selection", async () => {
    const onSelection = vi.fn();
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} enableSelection onSelectionChange={onSelection} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Select row 2" }));
    expect(onSelection).toHaveBeenLastCalledWith([ROWS[1]]);
    expect(screen.getByText(/1 selected/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select all rows" }));
    expect(onSelection).toHaveBeenLastCalledWith(ROWS);
    expect(bodyRows().every((r) => r.getAttribute("aria-selected") === "true")).toBe(true);
  });

  it("hides and pins columns from the Columns menu", async () => {
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Columns" }));
    await userEvent.click(screen.getByRole("menuitemcheckbox", { name: "Manufacturer" }));
    await userEvent.click(screen.getByRole("button", { name: "Pin Qty left" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("columnheader", { name: /Manufacturer/ })).not.toBeInTheDocument();
    const headers = screen.getAllByRole("columnheader").filter((h) => h.getAttribute("scope") === "col");
    expect(headers[0]).toHaveTextContent("Qty");
    expect(headers[0]).toHaveStyle({ position: "sticky", left: "0px" });
  });

  it("exports the filtered, sorted, visible data to CSV", async () => {
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} exportFileName="tracker" />);
    await userEvent.type(screen.getByRole("textbox", { name: "Filter Qty" }), "0");
    await userEvent.click(within(screen.getByRole("columnheader", { name: /MPN/ })).getByRole("button"));
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Export CSV" }));
    await waitFor(() => expect(blobs).toHaveLength(1));
    const text = await blobs[0]!.text();
    expect(text).toBe(
      "MPN,Manufacturer,Qty\r\n" +
        "BSS138,\"onsemi, Inc.\",50\r\n" +
        "GRM188R71H104KA93D,Murata,1200\r\n" +
        "RC0603FR-0710KL,Yageo,300\r\n",
    );
    expect(await screen.findByText("Exported 3 rows to CSV")).toBeInTheDocument();
  });

  it("exports XLSX with typed numeric cells", async () => {
    renderUi(<DataTable id="t" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} />);
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Export XLSX" }));
    await waitFor(() => expect(blobs).toHaveLength(1));
    const files = unzipSync(new Uint8Array(await blobs[0]!.arrayBuffer()));
    const sheet = strFromU8(files["xl/worksheets/sheet1.xml"]!);
    const shared = strFromU8(files["xl/sharedStrings.xml"] ?? new Uint8Array());
    expect(shared + sheet).toContain("STM32F407VGT6");
    expect(shared + sheet).toContain("onsemi, Inc.");
    expect(sheet).toMatch(/<c r="C3"[^>]*><v>1200<\/v><\/c>/);
  });

  it("saves and re-applies a view", async () => {
    renderUi(<DataTable id="views" data={ROWS} columns={COLUMNS} getRowId={(r) => r.id} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Filter Manufacturer" }), "yag");
    await userEvent.click(screen.getByRole("button", { name: "Save view" }));
    const name = screen.getByRole("textbox", { name: "View name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Yageo only{Enter}");
    expect(JSON.parse(localStorage.getItem("fabtrack.table-views.views") ?? "[]")[0].name).toBe("Yageo only");
    await userEvent.clear(screen.getByRole("textbox", { name: "Filter Manufacturer" }));
    expect(screen.getByText("4 of 4 rows")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Saved view" }), "Yageo only");
    expect(firstColumn()).toEqual(["RC0603FR-0710KL"]);
  });

  it("renders loading, error and empty states", () => {
    const { rerender } = renderUi(<DataTable id="t" data={[]} columns={COLUMNS} getRowId={(r) => r.id} loading />);
    expect(document.querySelectorAll("tbody .skeleton-shimmer").length).toBeGreaterThan(0);
    rerender(<DataTable id="t" data={[]} columns={COLUMNS} getRowId={(r) => r.id} error="Server returned 503" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server returned 503");
    rerender(<DataTable id="t" data={[]} columns={COLUMNS} getRowId={(r) => r.id} emptyState={<p>No BOQ lines yet</p>} />);
    expect(screen.getByText("No BOQ lines yet")).toBeInTheDocument();
  });

  it("virtualises 10,000 rows: only a window is in the DOM, exports include all", async () => {
    // jsdom has no layout: give elements a real size so the virtualiser computes a window.
    const h = vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(360);
    const w = vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(1200);
    const many: Line[] = Array.from({ length: 10_000 }, (_, i) => ({ id: String(i), mpn: `MPN-${i}`, manufacturer: "X", qty: i }));
    renderUi(<DataTable id="big" data={many} columns={COLUMNS} getRowId={(r) => r.id} maxHeight={360} />);
    expect(screen.getByText("10,000 of 10,000 rows")).toBeInTheDocument();
    expect(screen.getByTestId("big-scroll")).toHaveAttribute("data-virtualized", "true");
    const rendered = bodyRows().length;
    expect(rendered).toBeGreaterThan(5);
    expect(rendered).toBeLessThan(60);
    expect(firstColumn()[0]).toBe("MPN-0");
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Export CSV" }));
    await waitFor(() => expect(blobs).toHaveLength(1));
    expect((await blobs[0]!.text()).trim().split("\r\n")).toHaveLength(10_001);
    h.mockRestore();
    w.mockRestore();
  });
});

describe("toCsv", () => {
  it("quotes commas, quotes, newlines and edge whitespace (RFC 4180)", () => {
    expect(
      toCsv([{ header: "a" }, { header: "b,c" }], [["x \"y\"", "line1\nline2"], [" lead", null], [new Date("2026-11-04T00:00:00Z"), 3]]),
    ).toBe('a,"b,c"\r\n"x ""y""","line1\nline2"\r\n" lead",\r\n2026-11-04,3\r\n');
  });
});

describe("DataTable printing", () => {
  it("renders every row while printing a virtualised table", async () => {
    const many: Line[] = Array.from({ length: 500 }, (_, i) => ({ id: String(i), mpn: `P-${i}`, manufacturer: "X", qty: i }));
    renderUi(<DataTable id="print" data={many} columns={COLUMNS} getRowId={(r) => r.id} />);
    expect(screen.getByTestId("print-scroll")).toHaveAttribute("data-virtualized", "true");
    window.dispatchEvent(new Event("beforeprint"));
    await waitFor(() => expect(bodyRows()).toHaveLength(500));
    window.dispatchEvent(new Event("afterprint"));
    await waitFor(() => expect(screen.getByTestId("print-scroll")).toHaveAttribute("data-virtualized", "true"));
  });
});

describe("DataTable cell identity", () => {
  it("keeps cell elements when the parent re-renders with new column functions", async () => {
    let rerender: (() => void) | null = null;
    const clicked = vi.fn();
    function Host() {
      const [n, setN] = React.useState(0);
      rerender = () => setN((x) => x + 1);
      // Columns rebuilt on every render, as pages often do.
      const cols: ColumnDef<{ id: string }, unknown>[] = [
        { accessorKey: "id", header: "Id" },
        { id: "act", header: "", cell: ({ row }) => <button type="button" onClick={() => clicked(row.original.id)}>Act {row.original.id} {n >= 0 ? "" : "x"}</button> },
      ];
      return <DataTable id="identity" data={[{ id: "a" }]} columns={cols} getRowId={(r) => r.id} />;
    }
    renderUi(<Host />);
    const before = await screen.findByRole("button", { name: /Act a/ });
    act(() => rerender?.());
    expect(before.isConnected).toBe(true); // not remounted, so a click in flight still lands
    await userEvent.click(before);
    expect(clicked).toHaveBeenCalledWith("a");
  });
});

import { useVirtualizer } from "@tanstack/react-virtual";
import { Plus, Trash2 } from "lucide-react";
import * as React from "react";

import { Button, Dialog, DialogContent, Field, Input, Select, toast } from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError, apiPost } from "@/lib/api";
import { cn } from "@/lib/utils";

import { type BoqLine, CATEGORIES, type LineInput, type PartHit, searchParts } from "./api";

/** Editable columns, in order. `kind` drives the cell editor and paste parsing. */
export const GRID_COLUMNS = [
  { key: "ref_des", label: "Ref des", width: 150, kind: "text" },
  { key: "qty_per_unit", label: "Qty / unit", width: 90, kind: "number" },
  { key: "mpn", label: "MPN", width: 190, kind: "mpn" },
  { key: "manufacturer", label: "Manufacturer", width: 150, kind: "text" },
  { key: "description", label: "Description", width: 220, kind: "text" },
  { key: "value", label: "Value", width: 80, kind: "text" },
  { key: "package", label: "Package", width: 100, kind: "text" },
  { key: "category", label: "Category", width: 120, kind: "category" },
  { key: "unit", label: "Unit", width: 60, kind: "text" },
  { key: "dnp", label: "DNP", width: 50, kind: "bool" },
  { key: "attrition_pct", label: "Attrition %", width: 90, kind: "number" },
  { key: "unit_price", label: "Unit price", width: 90, kind: "number" },
  { key: "notes", label: "Notes", width: 180, kind: "text" },
] as const;

type ColumnKey = (typeof GRID_COLUMNS)[number]["key"];

export interface GridRow {
  key: string;
  line_key: string | null;
  part_id: string | null;
  values: Record<ColumnKey, string>;
}

const ROW_H = 34;
const TRUE = new Set(["y", "yes", "true", "1", "x", "dnp"]);

let tempId = 0;
export function emptyRow(): GridRow {
  tempId += 1;
  const values = Object.fromEntries(GRID_COLUMNS.map((c) => [c.key, ""])) as Record<ColumnKey, string>;
  values.unit = "pcs";
  return { key: `new-${tempId}`, line_key: null, part_id: null, values };
}

export function rowsFromLines(lines: BoqLine[]): GridRow[] {
  return lines.map((l) => ({
    key: l.line_key,
    line_key: l.line_key,
    part_id: l.part_id,
    values: {
      ref_des: l.ref_des ?? "",
      qty_per_unit: String(Number(l.qty_per_unit)),
      mpn: l.mpn ?? "",
      manufacturer: l.manufacturer ?? "",
      description: l.description ?? "",
      value: l.value ?? "",
      package: l.package ?? "",
      category: l.category ?? "",
      unit: l.unit,
      dnp: l.dnp ? "Y" : "",
      attrition_pct: l.attrition_override ? String(Number(l.attrition_pct)) : "",
      unit_price: l.unit_price === null ? "" : String(Number(l.unit_price)),
      notes: l.notes ?? "",
    },
  }));
}

const blank = (s: string) => (s.trim() === "" ? null : s.trim());

/** Grid rows → API payload. Rows with every cell empty are dropped. */
export function rowsToInput(rows: GridRow[]): LineInput[] {
  return rows
    .filter((r) => GRID_COLUMNS.some((c) => c.key !== "unit" && r.values[c.key].trim() !== ""))
    .map((r) => ({
      line_key: r.line_key,
      part_id: r.part_id,
      ref_des: blank(r.values.ref_des),
      qty_per_unit: r.values.qty_per_unit.trim() || "0",
      mpn: blank(r.values.mpn),
      manufacturer: blank(r.values.manufacturer),
      description: blank(r.values.description),
      value: blank(r.values.value),
      package: blank(r.values.package),
      category: blank(r.values.category),
      unit: r.values.unit.trim() || "pcs",
      dnp: TRUE.has(r.values.dnp.trim().toLowerCase()),
      attrition_pct: blank(r.values.attrition_pct),
      unit_price: blank(r.values.unit_price),
      notes: blank(r.values.notes),
    }));
}

/** Tab/newline separated text (Excel copy) → matrix. */
export function parseClipboard(text: string): string[][] {
  const rows = text.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n");
  return rows.map((r) => r.split("\t"));
}

function CreatePartDialog({ mpn, open, onClose, onCreated }: { mpn: string; open: boolean; onClose: () => void; onCreated: (p: PartHit) => void }) {
  const [form, setForm] = React.useState({ manufacturer: "", description: "", package: "", category: "Other" });
  const [saving, setSaving] = React.useState(false);
  const save = async () => {
    setSaving(true);
    try {
      const part = await apiPost<PartHit>("/parts", { mpn, ...form, manufacturer: form.manufacturer || null, package: form.package || null });
      toast.success(`${part.mpn} added to the part master`);
      onCreated(part);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create the part");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`New part ${mpn}`}
        description="Not in the part master yet. Add it so purchasing and stores can use it."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => void save()} loading={saving} disabled={!form.description.trim()}>Add part</Button>
          </>
        }
      >
        <div className="grid gap-3">
          <Field label="Manufacturer" htmlFor="np-mfr">
            <Input value={form.manufacturer} onChange={(e) => setForm((f) => ({ ...f, manufacturer: e.target.value }))} />
          </Field>
          <Field label="Description" htmlFor="np-desc" required>
            <Input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          </Field>
          <Field label="Package" htmlFor="np-pkg">
            <Input value={form.package} onChange={(e) => setForm((f) => ({ ...f, package: e.target.value }))} />
          </Field>
          <Field label="Category" htmlFor="np-cat">
            <Select value={form.category} onValueChange={(v) => setForm((f) => ({ ...f, category: v }))} options={CATEGORIES.map((c) => ({ value: c, label: c }))} />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function MpnSuggestions({ query, onPick, onCreate, canCreate }: { query: string; onPick: (p: PartHit) => void; onCreate: () => void; canCreate: boolean }) {
  const [hits, setHits] = React.useState<{ q: string; parts: PartHit[] } | null>(null);
  React.useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    const controller = new AbortController();
    const t = window.setTimeout(() => {
      searchParts(q, controller.signal)
        .then((parts) => setHits({ q, parts }))
        .catch(() => undefined);
    }, 150);
    return () => {
      controller.abort();
      window.clearTimeout(t);
    };
  }, [query]);
  if (query.trim().length < 2 || !hits || hits.q !== query.trim()) return null;
  return (
    <ul role="listbox" aria-label="Matching parts" className="absolute left-0 top-full z-dropdown mt-1 max-h-64 w-[26rem] overflow-y-auto rounded-md border bg-white p-1 shadow-md">
      {hits.parts.map((p) => (
        <li key={p.id} role="option" aria-selected="false">
          <button
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              onPick(p);
            }}
            className="flex w-full flex-col rounded-sm px-2 py-1.5 text-left hover:bg-accent-50"
          >
            <span className="font-mono text-xs text-neutral-900">{p.mpn}</span>
            <span className="truncate text-xs text-neutral-500">{[p.manufacturer, p.description, p.package].filter(Boolean).join(" · ")}</span>
          </button>
        </li>
      ))}
      {hits.parts.every((p) => p.mpn.toUpperCase() !== query.trim().toUpperCase()) && canCreate && (
        <li role="option" aria-selected="false">
          <button
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              onCreate();
            }}
            className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs font-medium text-accent-700 hover:bg-accent-50"
          >
            <Plus className="size-3.5" aria-hidden="true" /> Create part “{query.trim()}”
          </button>
        </li>
      )}
      {hits.parts.length === 0 && !canCreate && <li className="px-2 py-1.5 text-xs text-neutral-500">No matching part</li>}
    </ul>
  );
}

export interface BoqGridProps {
  rows: GridRow[];
  onChange: (rows: GridRow[]) => void;
  /** Server validation problems: 1-based line numbers. */
  errorLines?: Set<number>;
  maxHeight?: number;
}

/** Spreadsheet-like BOQ editor: type, paste from Excel, arrow keys / Enter to move,
 *  MPN autocomplete against the part master. */
export function BoqGrid({ rows, onChange, errorLines, maxHeight = 520 }: BoqGridProps) {
  const canCreatePart = useCan("parts:manage");
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [active, setActive] = React.useState<{ row: number; col: number } | null>(null);
  const [creating, setCreating] = React.useState<{ row: number; mpn: string } | null>(null);
  const pendingFocus = React.useRef<{ row: number; col: number } | null>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 10,
    initialRect: { width: 1400, height: maxHeight },
  });
  const virtual = rows.length > 200;
  const items = virtual ? virtualizer.getVirtualItems() : rows.map((_, index) => ({ index, start: index * ROW_H, end: (index + 1) * ROW_H }));
  const padTop = virtual && items.length ? (items[0]?.start ?? 0) : 0;
  const padBottom = virtual && items.length ? virtualizer.getTotalSize() - (items[items.length - 1]?.end ?? 0) : 0;

  React.useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    const el = scrollRef.current?.querySelector<HTMLElement>(`[data-cell="${target.row}:${target.col}"]`);
    if (el) {
      el.focus();
      pendingFocus.current = null;
    }
  });

  const focusCell = (row: number, col: number) => {
    const r = Math.max(0, Math.min(rows.length - 1, row));
    const c = Math.max(0, Math.min(GRID_COLUMNS.length - 1, col));
    pendingFocus.current = { row: r, col: c };
    if (virtual) virtualizer.scrollToIndex(r);
    const el = scrollRef.current?.querySelector<HTMLElement>(`[data-cell="${r}:${c}"]`);
    if (el) {
      el.focus();
      pendingFocus.current = null;
    }
  };

  const setCell = (row: number, key: ColumnKey, value: string, extra?: Partial<GridRow>) => {
    const next = rows.slice();
    const current = next[row];
    if (!current) return;
    const values = { ...current.values, [key]: value };
    // Typing a different MPN unlinks the part until one is picked again.
    const part_id = key === "mpn" && extra?.part_id === undefined ? null : (extra?.part_id ?? current.part_id);
    next[row] = { ...current, ...extra, part_id, values };
    onChange(next);
  };

  const pickPart = (row: number, p: PartHit) => {
    const current = rows[row];
    if (!current) return;
    const next = rows.slice();
    next[row] = {
      ...current,
      part_id: p.id,
      values: {
        ...current.values,
        mpn: p.mpn,
        manufacturer: p.manufacturer ?? current.values.manufacturer,
        description: current.values.description || p.description,
        package: current.values.package || (p.package ?? ""),
        value: current.values.value || (p.value ?? ""),
        category: current.values.category || p.category,
        unit: current.values.unit || p.unit,
      },
    };
    onChange(next);
    setActive(null);
  };

  const paste = (row: number, col: number, text: string) => {
    const matrix = parseClipboard(text);
    const next = rows.slice();
    matrix.forEach((cells, i) => {
      const r = row + i;
      while (next.length <= r) next.push(emptyRow());
      const current = next[r];
      if (!current) return;
      const values = { ...current.values };
      cells.forEach((cell, j) => {
        const column = GRID_COLUMNS[col + j];
        if (column) values[column.key] = cell.trim();
      });
      next[r] = { ...current, part_id: cells.length && col <= 2 && col + cells.length > 2 ? null : current.part_id, values };
    });
    onChange(next);
    toast.success(`Pasted ${matrix.length} row${matrix.length === 1 ? "" : "s"}`);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, row: number, col: number) => {
    const el = e.currentTarget;
    const atStart = el.selectionStart === 0 && el.selectionEnd === 0;
    const atEnd = el.selectionStart === el.value.length;
    if (e.key === "ArrowDown" || (e.key === "Enter" && !e.shiftKey)) {
      e.preventDefault();
      if (row === rows.length - 1 && e.key === "Enter") {
        onChange([...rows, emptyRow()]);
        pendingFocus.current = { row: row + 1, col };
      } else focusCell(row + 1, col);
    } else if (e.key === "ArrowUp" || (e.key === "Enter" && e.shiftKey)) {
      e.preventDefault();
      focusCell(row - 1, col);
    } else if (e.key === "ArrowLeft" && atStart) {
      e.preventDefault();
      focusCell(row, col - 1);
    } else if (e.key === "ArrowRight" && atEnd) {
      e.preventDefault();
      focusCell(row, col + 1);
    } else if (e.key === "Escape") {
      setActive(null);
    }
  };

  return (
    <div className="rounded-lg border bg-white shadow-sm">
      <div ref={scrollRef} className="relative overflow-auto" style={{ maxHeight }}>
        <table className="table-fixed border-separate border-spacing-0 text-sm" role="grid" aria-label="BOQ lines editor" aria-rowcount={rows.length}>
          <colgroup>
            <col style={{ width: 44 }} />
            {GRID_COLUMNS.map((c) => (
              <col key={c.key} style={{ width: c.width }} />
            ))}
            <col style={{ width: 40 }} />
          </colgroup>
          <thead className="sticky top-0 z-sticky bg-neutral-50">
            <tr>
              <th scope="col" className="h-8 border-b px-2 text-right text-xs font-semibold text-neutral-500">#</th>
              {GRID_COLUMNS.map((c) => (
                <th key={c.key} scope="col" className="h-8 border-b border-l border-neutral-200 px-2 text-left text-xs font-semibold text-neutral-600">
                  {c.label}
                </th>
              ))}
              <th scope="col" className="border-b"><span className="sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody>
            {padTop > 0 && <tr aria-hidden="true" style={{ height: padTop }} />}
            {items.map(({ index: r }) => {
              const row = rows[r];
              if (!row) return null;
              const bad = errorLines?.has(r + 1);
              return (
                <tr key={row.key} style={{ height: ROW_H }} aria-rowindex={r + 1} className={cn(bad && "bg-status-red-bg")}>
                  <td className={cn("border-b border-neutral-100 px-2 text-right font-mono text-xs tabular-nums", bad ? "text-status-red-fg" : "text-neutral-400")}>
                    {r + 1}
                  </td>
                  {GRID_COLUMNS.map((c, ci) => {
                    const common = {
                      "data-cell": `${r}:${ci}`,
                      "aria-label": `${c.label}, line ${r + 1}`,
                      onFocus: () => setActive({ row: r, col: ci }),
                      onPaste: (e: React.ClipboardEvent) => {
                        const text = e.clipboardData.getData("text/plain");
                        if (text.includes("\t") || text.includes("\n")) {
                          e.preventDefault();
                          paste(r, ci, text);
                        }
                      },
                    };
                    const cellClass = "h-[33px] w-full border-0 bg-transparent px-2 text-sm outline-none focus:bg-accent-50/60 focus:ring-2 focus:ring-inset focus:ring-accent-600";
                    let editor: React.ReactNode;
                    if (c.kind === "bool") {
                      editor = (
                        <input
                          type="checkbox"
                          {...common}
                          checked={TRUE.has(row.values.dnp.toLowerCase())}
                          onChange={(e) => setCell(r, c.key, e.target.checked ? "Y" : "")}
                          onKeyDown={(e) => {
                            if (e.key === "ArrowDown" || e.key === "Enter") focusCell(r + 1, ci);
                            if (e.key === "ArrowUp") focusCell(r - 1, ci);
                            if (e.key === "ArrowLeft") focusCell(r, ci - 1);
                            if (e.key === "ArrowRight") focusCell(r, ci + 1);
                          }}
                          className="mx-auto block size-4 accent-accent-600"
                        />
                      );
                    } else if (c.kind === "category") {
                      editor = (
                        <>
                          <input {...common} list="boq-categories" value={row.values.category} onChange={(e) => setCell(r, c.key, e.target.value)} onKeyDown={(e) => onKeyDown(e, r, ci)} className={cellClass} />
                        </>
                      );
                    } else {
                      editor = (
                        <input
                          {...common}
                          inputMode={c.kind === "number" ? "decimal" : undefined}
                          value={row.values[c.key]}
                          placeholder={c.key === "attrition_pct" ? "category" : undefined}
                          onChange={(e) => setCell(r, c.key, e.target.value)}
                          onKeyDown={(e) => onKeyDown(e, r, ci)}
                          onBlur={() => c.kind === "mpn" && window.setTimeout(() => setActive((a) => (a?.row === r && a.col === ci ? null : a)), 150)}
                          className={cn(cellClass, (c.kind === "number" || c.kind === "mpn" || c.key === "ref_des") && "font-mono text-[12.5px]", c.kind === "number" && "text-right tabular-nums", c.kind === "mpn" && row.part_id && "text-accent-800")}
                        />
                      );
                    }
                    return (
                      <td key={c.key} className="relative border-b border-l border-neutral-100 p-0">
                        {editor}
                        {c.kind === "mpn" && active?.row === r && active.col === ci && (
                          <MpnSuggestions
                            query={row.values.mpn}
                            canCreate={canCreatePart}
                            onPick={(p) => pickPart(r, p)}
                            onCreate={() => setCreating({ row: r, mpn: row.values.mpn.trim() })}
                          />
                        )}
                      </td>
                    );
                  })}
                  <td className="border-b border-neutral-100 text-center">
                    <button
                      type="button"
                      aria-label={`Remove line ${r + 1}`}
                      onClick={() => onChange(rows.filter((_, i) => i !== r))}
                      className="rounded p-1 text-neutral-400 hover:bg-neutral-100 hover:text-status-red-fg"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
            {padBottom > 0 && <tr aria-hidden="true" style={{ height: padBottom }} />}
          </tbody>
        </table>
        <datalist id="boq-categories">
          {CATEGORIES.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </div>
      <div className="flex items-center gap-2 border-t px-3 py-2">
        <Button size="sm" variant="secondary" onClick={() => onChange([...rows, emptyRow()])}>
          <Plus /> Add row
        </Button>
        <span className="text-xs text-neutral-500">Paste rows copied from Excel into any cell. Enter on the last row adds a new one.</span>
      </div>
      {creating && (
        <CreatePartDialog
          mpn={creating.mpn}
          open
          onClose={() => setCreating(null)}
          onCreated={(p) => {
            pickPart(creating.row, p);
            setCreating(null);
          }}
        />
      )}
    </div>
  );
}

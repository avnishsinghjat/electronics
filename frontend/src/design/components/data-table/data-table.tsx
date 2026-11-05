import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  type Column,
  type ColumnDef,
  type ColumnFiltersState,
  type ColumnPinningState,
  type Row,
  type RowData,
  type RowSelectionState,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Bookmark,
  Columns3,
  Download,
  Pin,
  PinOff,
  Search,
  Trash2,
} from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { Button } from "../button";
import { Checkbox } from "../checkbox";
import { controlClasses } from "../field";
import { Skeleton } from "../feedback";
import { Dialog, DialogContent, toast } from "../overlay";
import { type CellValue, type ExportColumn, csvBlob, downloadBlob, xlsxBlob } from "./export";
import { type SavedView, loadViews, storeViews, upsertView } from "./saved-views";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Header text used in menus and exports. */
    label?: string;
    /** Render cells in JetBrains Mono (MPNs, serials, quantities). */
    mono?: boolean;
    align?: "left" | "right" | "center";
    /** Show a text filter for this column (default true for accessor columns). */
    filter?: boolean;
    exportType?: ExportColumn["type"];
    /** Value written to CSV/XLSX; defaults to the accessor value. */
    exportValue?: (row: TData) => CellValue;
  }
}

export const ROW_HEIGHT = 36;
/** Below this many rows every row is rendered; above it rows are virtualised. */
export const VIRTUALIZE_THRESHOLD = 300;
const SELECT_COLUMN_ID = "__select";

/** True while the browser prints, so virtualised tables print every row. */
function usePrinting(): boolean {
  const [printing, setPrinting] = React.useState(false);
  React.useEffect(() => {
    const on = () => setPrinting(true);
    const off = () => setPrinting(false);
    window.addEventListener("beforeprint", on);
    window.addEventListener("afterprint", off);
    return () => {
      window.removeEventListener("beforeprint", on);
      window.removeEventListener("afterprint", off);
    };
  }, []);
  return printing;
}

export interface DataTableProps<T> {
  /** Stable id: saved views are stored under it. */
  id: string;
  data: T[];
  columns: ColumnDef<T, unknown>[];
  getRowId: (row: T) => string;
  loading?: boolean;
  error?: string | null;
  emptyState?: React.ReactNode;
  enableSelection?: boolean;
  onSelectionChange?: (rows: T[]) => void;
  exportFileName?: string;
  /** Max height of the scroll area; rows beyond it are virtualised. */
  maxHeight?: number;
  toolbar?: React.ReactNode;
  initialSorting?: SortingState;
  initialPinning?: ColumnPinningState;
}

function columnLabel<T>(column: Column<T, unknown>): string {
  const meta = column.columnDef.meta;
  if (meta?.label) return meta.label;
  return typeof column.columnDef.header === "string" ? column.columnDef.header : column.id;
}

function exportRows<T>(rows: Row<T>[], columns: Column<T, unknown>[]): CellValue[][] {
  return rows.map((row) =>
    columns.map((col) => {
      const meta = col.columnDef.meta;
      if (meta?.exportValue) return meta.exportValue(row.original);
      const v = row.getValue(col.id);
      return v instanceof Date || typeof v === "number" || typeof v === "boolean" || typeof v === "string" || v == null
        ? (v as CellValue)
        : String(v);
    }),
  );
}

export function DataTable<T>({
  id,
  data,
  columns,
  getRowId,
  loading = false,
  error = null,
  emptyState,
  enableSelection = false,
  onSelectionChange,
  exportFileName,
  maxHeight = 560,
  toolbar,
  initialSorting = [],
  initialPinning = { left: [], right: [] },
}: DataTableProps<T>) {
  const [sorting, setSorting] = React.useState<SortingState>(initialSorting);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [columnPinning, setColumnPinning] = React.useState<ColumnPinningState>(() => ({
    left: enableSelection ? [SELECT_COLUMN_ID, ...(initialPinning.left ?? [])] : (initialPinning.left ?? []),
    right: initialPinning.right ?? [],
  }));
  const [globalFilter, setGlobalFilter] = React.useState("");
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const [views, setViews] = React.useState<SavedView[]>(() => loadViews(id));
  const [activeView, setActiveView] = React.useState<string>("");
  const [saveOpen, setSaveOpen] = React.useState(false);
  const [viewName, setViewName] = React.useState("");

  const allColumns = React.useMemo<ColumnDef<T, unknown>[]>(() => {
    if (!enableSelection) return columns;
    const select: ColumnDef<T, unknown> = {
      id: SELECT_COLUMN_ID,
      size: 40,
      enableSorting: false,
      enableHiding: false,
      enableColumnFilter: false,
      meta: { filter: false, label: "Select" },
      header: ({ table }) => (
        <Checkbox
          aria-label="Select all rows"
          checked={table.getIsAllRowsSelected() ? true : table.getIsSomeRowsSelected() ? "indeterminate" : false}
          onCheckedChange={(v) => table.toggleAllRowsSelected(v === true)}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          aria-label={`Select row ${row.id}`}
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(v === true)}
        />
      ),
    };
    return [select, ...columns];
  }, [columns, enableSelection]);

  const table = useReactTable({
    data,
    columns: allColumns,
    getRowId: (row) => getRowId(row),
    state: { sorting, columnFilters, columnVisibility, columnPinning, globalFilter, rowSelection },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnPinningChange: setColumnPinning,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: enableSelection,
    globalFilterFn: "includesString",
    sortDescFirst: false,
    defaultColumn: { size: 160, minSize: 60, filterFn: "includesString" },
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const rows = table.getRowModel().rows;

  React.useEffect(() => {
    onSelectionChange?.(table.getSelectedRowModel().rows.map((r) => r.original));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowSelection]);

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
    initialRect: { width: 1200, height: maxHeight },
  });
  const printing = usePrinting();
  const virtualize = rows.length > VIRTUALIZE_THRESHOLD && !printing;
  const virtualRows = virtualize
    ? virtualizer.getVirtualItems()
    : rows.map((_, index) => ({ index, start: index * ROW_HEIGHT, end: (index + 1) * ROW_HEIGHT }));
  const padTop = virtualize && virtualRows.length ? (virtualRows[0]?.start ?? 0) : 0;
  const padBottom =
    virtualize && virtualRows.length ? virtualizer.getTotalSize() - (virtualRows[virtualRows.length - 1]?.end ?? 0) : 0;

  const visibleColumns = table.getVisibleLeafColumns();
  const exportColumns = visibleColumns.filter((c) => c.id !== SELECT_COLUMN_ID);

  const doExport = async (kind: "csv" | "xlsx") => {
    const cols: ExportColumn[] = exportColumns.map((c) => ({ header: columnLabel(c), type: c.columnDef.meta?.exportType }));
    const body = exportRows(table.getSortedRowModel().rows, exportColumns);
    const base = exportFileName ?? id;
    try {
      const blob = kind === "csv" ? csvBlob(cols, body) : await xlsxBlob(cols, body);
      downloadBlob(blob, `${base}.${kind}`);
      toast.success(`Exported ${body.length} rows to ${kind.toUpperCase()}`);
    } catch (err) {
      toast.error(`Export failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  };

  const applyView = (name: string) => {
    const view = views.find((v) => v.name === name);
    setActiveView(name);
    if (!view) return;
    setSorting(view.sorting);
    setColumnFilters(view.columnFilters);
    setColumnVisibility(view.columnVisibility);
    setColumnPinning(view.columnPinning);
    setGlobalFilter(view.globalFilter);
  };

  const saveView = (raw: string) => {
    const name = raw.trim();
    if (!name) return;
    setSaveOpen(false);
    const next = upsertView(views, { name, sorting, columnFilters, columnVisibility, columnPinning, globalFilter });
    setViews(next);
    setActiveView(name);
    if (storeViews(id, next)) toast.success(`View "${name}" saved`);
    else toast.error("This browser blocked saving the view");
  };

  const deleteView = () => {
    if (!activeView) return;
    const next = views.filter((v) => v.name !== activeView);
    setViews(next);
    storeViews(id, next);
    toast.success(`View "${activeView}" deleted`);
    setActiveView("");
  };

  const pinStyle = (column: Column<T, unknown>): React.CSSProperties => {
    const pinned = column.getIsPinned();
    if (!pinned) return { width: column.getSize() };
    return {
      width: column.getSize(),
      position: "sticky",
      left: pinned === "left" ? column.getStart("left") : undefined,
      right: pinned === "right" ? column.getAfter("right") : undefined,
      zIndex: 1,
    };
  };

  const hasFilters = visibleColumns.some((c) => c.getCanFilter() && c.columnDef.meta?.filter !== false);
  const filteredCount = table.getFilteredRowModel().rows.length;
  const selectedCount = Object.keys(rowSelection).length;

  return (
    <div className="flex flex-col rounded-lg border bg-white shadow-sm" data-card="">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2" data-print="hide">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" />
          <input
            aria-label="Search table"
            placeholder="Search…"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            className={cn(controlClasses, "h-8 w-56 pl-8")}
          />
        </div>
        {toolbar}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="mr-1 text-xs tabular-nums text-neutral-500" aria-live="polite">
            {selectedCount > 0 ? `${selectedCount} selected · ` : ""}
            {filteredCount.toLocaleString("en-IN")} of {data.length.toLocaleString("en-IN")} rows
          </span>
          <select
            aria-label="Saved view"
            value={activeView}
            onChange={(e) => applyView(e.target.value)}
            className={cn(controlClasses, "h-8 w-36 px-2 text-xs")}
          >
            <option value="">Default view</option>
            {views.map((v) => (
              <option key={v.name} value={v.name}>
                {v.name}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Save view"
            onClick={() => {
              setViewName(activeView || "My view");
              setSaveOpen(true);
            }}
          >
            <Bookmark />
          </Button>
          {activeView && (
            <Button variant="ghost" size="icon-sm" aria-label="Delete view" onClick={deleteView}>
              <Trash2 />
            </Button>
          )}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="secondary" size="sm" aria-label="Columns">
                <Columns3 /> Columns
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={4} className="z-dropdown min-w-56 rounded-md border bg-white p-1 shadow-md">
                <DropdownMenu.Label className="px-2 py-1 text-xs font-medium text-neutral-500">Show and pin columns</DropdownMenu.Label>
                {table
                  .getAllLeafColumns()
                  .filter((c) => c.id !== SELECT_COLUMN_ID)
                  .map((col) => (
                    <div key={col.id} className="flex items-center gap-1 pr-1">
                      <DropdownMenu.CheckboxItem
                        checked={col.getIsVisible()}
                        disabled={!col.getCanHide()}
                        onSelect={(e) => e.preventDefault()}
                        onCheckedChange={(v) => col.toggleVisibility(v)}
                        className="flex flex-1 cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-neutral-100"
                      >
                        <span className={cn("flex size-4 items-center justify-center rounded border", col.getIsVisible() ? "border-accent-600 bg-accent-600" : "border-neutral-400")}>
                          <DropdownMenu.ItemIndicator>
                            <svg viewBox="0 0 12 12" className="size-3 fill-none stroke-white stroke-[2]"><path d="M2.5 6.5l2.2 2.2L9.5 3.8" /></svg>
                          </DropdownMenu.ItemIndicator>
                        </span>
                        {columnLabel(col)}
                      </DropdownMenu.CheckboxItem>
                      <button
                        type="button"
                        aria-label={col.getIsPinned() ? `Unpin ${columnLabel(col)}` : `Pin ${columnLabel(col)} left`}
                        onClick={() => col.pin(col.getIsPinned() ? false : "left")}
                        className="rounded p-1 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900"
                      >
                        {col.getIsPinned() ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
                      </button>
                    </div>
                  ))}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="secondary" size="sm" aria-label="Export">
                <Download /> Export
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={4} className="z-dropdown min-w-40 rounded-md border bg-white p-1 shadow-md">
                <DropdownMenu.Item onSelect={() => void doExport("csv")} className="cursor-default rounded-sm px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-neutral-100">
                  Export CSV
                </DropdownMenu.Item>
                <DropdownMenu.Item onSelect={() => void doExport("xlsx")} className="cursor-default rounded-sm px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-neutral-100">
                  Export XLSX
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent
          size="sm"
          title="Save view"
          description="Saves the current sorting, filters, visible and pinned columns in this browser."
          footer={
            <>
              <Button variant="secondary" onClick={() => setSaveOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => saveView(viewName)} disabled={!viewName.trim()}>
                Save view
              </Button>
            </>
          }
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              saveView(viewName);
            }}
          >
            <label htmlFor={`${id}-view-name`} className="text-sm font-medium text-neutral-700">
              View name
            </label>
            <input
              id={`${id}-view-name`}
              autoFocus
              value={viewName}
              onChange={(e) => setViewName(e.target.value)}
              className={cn(controlClasses, "mt-1.5 h-9")}
            />
          </form>
        </DialogContent>
      </Dialog>

      <div
        ref={scrollRef}
        className="relative overflow-auto print:max-h-none print:overflow-visible"
        style={{ maxHeight: printing ? undefined : maxHeight }}
        data-testid={`${id}-scroll`}
        data-virtualized={virtualize || undefined}
      >
        <table className="w-full table-fixed border-separate border-spacing-0 text-sm" style={{ minWidth: table.getTotalSize() }}>
          <thead className="sticky top-0 z-sticky bg-neutral-50">
            <tr>
              {table.getHeaderGroups()[0]?.headers.map((header) => {
                const col = header.column;
                const sorted = col.getIsSorted();
                const align = col.columnDef.meta?.align ?? "left";
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : col.getCanSort() ? "none" : undefined}
                    style={pinStyle(col)}
                    className={cn(
                      "h-9 border-b bg-neutral-50 px-3 text-left text-xs font-semibold text-neutral-600",
                      align === "right" && "text-right",
                      align === "center" && "text-center",
                      col.getIsPinned() && "border-r",
                    )}
                  >
                    {header.isPlaceholder ? null : col.getCanSort() ? (
                      <button
                        type="button"
                        onClick={col.getToggleSortingHandler()}
                        className={cn("inline-flex items-center gap-1 rounded hover:text-neutral-900 focus-visible:shadow-focus focus-visible:outline-none", align === "right" && "flex-row-reverse")}
                      >
                        {flexRender(col.columnDef.header, header.getContext())}
                        {sorted === "asc" ? <ArrowUp className="size-3" /> : sorted === "desc" ? <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 text-neutral-400" />}
                      </button>
                    ) : (
                      flexRender(col.columnDef.header, header.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
            {hasFilters && (
              <tr data-print="hide">
                {table.getHeaderGroups()[0]?.headers.map((header) => {
                  const col = header.column;
                  const show = col.getCanFilter() && col.columnDef.meta?.filter !== false;
                  return (
                    <th key={header.id} style={pinStyle(col)} className={cn("border-b bg-neutral-50 px-2 pb-1.5", col.getIsPinned() && "border-r")}>
                      {show && (
                        <input
                          aria-label={`Filter ${columnLabel(col)}`}
                          value={(col.getFilterValue() as string | undefined) ?? ""}
                          onChange={(e) => col.setFilterValue(e.target.value || undefined)}
                          placeholder="Filter"
                          className="h-7 w-full rounded border border-neutral-200 bg-white px-2 text-xs font-normal text-neutral-800 placeholder:text-neutral-400 focus:border-accent-600 focus:outline-none"
                        />
                      )}
                    </th>
                  );
                })}
              </tr>
            )}
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 8 }, (_, i) => (
                <tr key={`sk-${i}`} style={{ height: ROW_HEIGHT }}>
                  {visibleColumns.map((c) => (
                    <td key={c.id} className="border-b px-3">
                      <Skeleton className="h-3.5 w-3/4" />
                    </td>
                  ))}
                </tr>
              ))
            ) : error ? (
              <tr>
                <td colSpan={visibleColumns.length} className="px-3 py-10 text-center">
                  <p role="alert" className="text-sm font-medium text-status-red-fg">{error}</p>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={visibleColumns.length}>
                  {data.length > 0 ? (
                    <p className="px-3 py-10 text-center text-sm text-neutral-500">No rows match the current filters.</p>
                  ) : (
                    (emptyState ?? <p className="px-3 py-10 text-center text-sm text-neutral-500">No records yet.</p>)
                  )}
                </td>
              </tr>
            ) : (
              <>
                {padTop > 0 && <tr data-virtual-spacer="" style={{ height: padTop }} aria-hidden="true" />}
                {virtualRows.map((vr) => {
                  const row = rows[vr.index];
                  if (!row) return null;
                  return (
                    <tr
                      key={row.id}
                      data-index={vr.index}
                      aria-selected={enableSelection ? row.getIsSelected() : undefined}
                      style={{ height: ROW_HEIGHT }}
                      className={cn("group", row.getIsSelected() ? "bg-accent-50/60" : "hover:bg-neutral-25")}
                    >
                      {row.getVisibleCells().map((cell) => {
                        const meta = cell.column.columnDef.meta;
                        return (
                          <td
                            key={cell.id}
                            style={pinStyle(cell.column)}
                            className={cn(
                              "truncate border-b border-neutral-100 px-3 text-neutral-800",
                              meta?.mono && "font-mono text-[12.5px] tabular-nums",
                              meta?.align === "right" && "text-right",
                              meta?.align === "center" && "text-center",
                              cell.column.getIsPinned() && "border-r border-r-neutral-200 bg-white group-hover:bg-neutral-25",
                            )}
                          >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
                {padBottom > 0 && <tr data-virtual-spacer="" style={{ height: padBottom }} aria-hidden="true" />}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import type {
  ColumnFiltersState,
  ColumnPinningState,
  SortingState,
  VisibilityState,
} from "@tanstack/react-table";

/** A named table configuration. Stored per browser (a per-viewer convenience). */
export interface SavedView {
  name: string;
  sorting: SortingState;
  columnFilters: ColumnFiltersState;
  columnVisibility: VisibilityState;
  columnPinning: ColumnPinningState;
  globalFilter: string;
}

const key = (tableId: string) => `fabtrack.table-views.${tableId}`;

export function loadViews(tableId: string): SavedView[] {
  try {
    const raw = window.localStorage.getItem(key(tableId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as SavedView[]).filter((v) => typeof v?.name === "string") : [];
  } catch {
    return [];
  }
}

export function storeViews(tableId: string, views: SavedView[]): boolean {
  try {
    window.localStorage.setItem(key(tableId), JSON.stringify(views));
    return true;
  } catch {
    return false;
  }
}

export function upsertView(views: SavedView[], view: SavedView): SavedView[] {
  const rest = views.filter((v) => v.name !== view.name);
  return [...rest, view].sort((a, b) => a.name.localeCompare(b.name));
}

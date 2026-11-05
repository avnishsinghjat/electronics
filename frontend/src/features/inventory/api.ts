import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPatch, apiPost, qs } from "@/lib/api";

export interface Location {
  id: string;
  code: string;
  name: string;
  kind: "stores" | "bin" | "msl_cabinet" | "wip" | "quarantine" | "scrap";
  parent_id: string | null;
}

export interface PartStock {
  part_id: string;
  mpn: string;
  manufacturer: string | null;
  description: string;
  category: string;
  unit: string;
  msl_level: number | null;
  min_stock: number | null;
  on_hand: string;
  usable: string;
  reserved: string;
  available: string;
  low: boolean;
  locations: string[];
  row_version: number;
}

export interface Balance {
  part_id: string;
  mpn: string;
  manufacturer: string | null;
  description: string;
  category: string;
  unit: string;
  msl_level: number | null;
  location_id: string;
  location_code: string;
  location_kind: Location["kind"];
  qty_on_hand: string;
}

export interface LedgerRow {
  id: number;
  created_at: string;
  part_id: string;
  mpn: string;
  location_code: string;
  qty_delta: string;
  reason: "GRN" | "ISSUE" | "RETURN" | "ADJUST" | "SCRAP" | "TRANSFER";
  ref_type: string | null;
  ref_id: string | null;
  ref_label: string | null;
  lot_code: string | null;
  project_code: string | null;
  note: string | null;
  user_name: string | null;
}

export interface Adjustment {
  id: string;
  part_id: string;
  mpn: string;
  location_id: string;
  location_code: string;
  qty_delta: string;
  reason: string;
  lot_code: string | null;
  status: "pending" | "approved" | "rejected";
  requested_by: string | null;
  requested_by_name: string | null;
  requested_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  row_version: number;
}

export interface Reservation {
  id: string;
  part_id: string;
  mpn: string;
  project_id: string;
  project_code: string;
  location_code: string | null;
  qty: string;
  status: "active" | "consumed" | "released";
  note: string | null;
  created_at: string;
  row_version: number;
}

export const LOCATION_KIND: Record<Location["kind"], string> = {
  stores: "Stores",
  bin: "Bin",
  msl_cabinet: "MSL dry cabinet",
  wip: "Production WIP",
  quarantine: "Quarantine",
  scrap: "Scrap",
};

export const invKeys = {
  all: ["inventory"] as const,
  locations: ["inventory", "locations"] as const,
  stock: (q: string, low: boolean) => ["inventory", "stock", q, low] as const,
  balances: (q: string, loc: string) => ["inventory", "balances", q, loc] as const,
  ledger: (f: object) => ["inventory", "ledger", f] as const,
  adjustments: (status: string) => ["inventory", "adjustments", status] as const,
  reservations: (projectId: string) => ["inventory", "reservations", projectId] as const,
};

export const useLocations = (enabled = true) =>
  useQuery({ queryKey: invKeys.locations, queryFn: ({ signal }) => apiGet<Location[]>("/inventory/locations", signal), staleTime: 60_000, enabled });
export const useStock = (q = "", lowOnly = false) =>
  useQuery({ queryKey: invKeys.stock(q, lowOnly), queryFn: ({ signal }) => apiGet<PartStock[]>(`/inventory/stock${qs({ q: q || null, low_only: lowOnly || null })}`, signal) });
export const useBalances = (q = "", locationId = "") =>
  useQuery({ queryKey: invKeys.balances(q, locationId), queryFn: ({ signal }) => apiGet<Balance[]>(`/inventory/balances${qs({ q: q || null, location_id: locationId || null })}`, signal) });
export const useLedger = (f: { part_id?: string; location_id?: string; reason?: string; project_id?: string; limit?: number }) =>
  useQuery({ queryKey: invKeys.ledger(f), queryFn: ({ signal }) => apiGet<{ items: LedgerRow[]; total: number }>(`/inventory/ledger${qs(f)}`, signal) });
export const useAdjustments = (status = "") =>
  useQuery({ queryKey: invKeys.adjustments(status), queryFn: ({ signal }) => apiGet<Adjustment[]>(`/inventory/adjustments${qs({ status: status || null })}`, signal) });
export const useReservations = (projectId = "") =>
  useQuery({ queryKey: invKeys.reservations(projectId), queryFn: ({ signal }) => apiGet<Reservation[]>(`/inventory/reservations${qs({ project_id: projectId || null })}`, signal) });

export function useInventoryMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: invKeys.all });
    void qc.invalidateQueries({ queryKey: ["procurement"] });
  };
  // Called in a fixed order on every render, like any hook.
  const useM = <A, R>(fn: (a: A) => Promise<R>) => useMutation({ mutationFn: fn, onSuccess: refresh });
  return {
    transfer: useM((b: { part_id: string; from_location_id: string; to_location_id: string; qty: string; lot_code: string | null; note: string | null }) =>
      apiPost<LedgerRow[]>("/inventory/transfers", b),
    ),
    requestAdjustment: useM((b: { part_id: string; location_id: string; qty_delta: string; reason: string; lot_code: string | null }) => apiPost<Adjustment>("/inventory/adjustments", b)),
    decideAdjustment: useM(({ id, ...b }: { id: string; row_version: number; approve: boolean; note: string | null }) => apiPost<Adjustment>(`/inventory/adjustments/${id}/decision`, b)),
    reserve: useM((b: { part_id: string; project_id: string; qty: string; location_id: string | null; note: string | null }) => apiPost<Reservation>("/inventory/reservations", b)),
    release: useM(({ id, row_version }: { id: string; row_version: number }) => apiPost<Reservation>(`/inventory/reservations/${id}/release`, { row_version })),
    setMinStock: useM(({ part_id, ...b }: { part_id: string; row_version: number; min_stock: number | null; msl_level: number | null }) => apiPatch(`/parts/${part_id}`, b)),
  };
}

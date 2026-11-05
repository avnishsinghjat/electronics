import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { StatusTone } from "@/design/tokens";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, qs } from "@/lib/api";

/* ---------------------------------------------------------------- types */

export interface Contact {
  name: string;
  role?: string | null;
  phone?: string | null;
  email?: string | null;
}

export interface Vendor {
  id: string;
  code: string;
  name: string;
  gstin: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  contacts: Contact[];
  payment_terms: string | null;
  lead_time_days: number | null;
  rating: string | null;
  notes: string | null;
  is_sample: boolean;
  open_po_count: number;
  row_version: number;
}

export type VendorInput = Omit<Vendor, "id" | "is_sample" | "open_po_count" | "row_version">;

export interface PoRef {
  id: string;
  number: string;
  status: string;
}

export interface Requisition {
  id: string;
  number: string;
  project_id: string;
  project_code: string;
  project_name: string;
  status: "draft" | "submitted" | "approved" | "rejected" | "converted";
  submitted_at: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  decision_note: string | null;
  notes: string | null;
  created_at: string;
  created_by_name: string | null;
  line_count: number;
  purchase_orders: PoRef[];
  row_version: number;
}

export interface RequisitionLine {
  id: string;
  boq_line_id: string | null;
  boq_ref: string | null;
  part_id: string;
  mpn: string;
  manufacturer: string | null;
  description: string;
  unit: string;
  qty: string;
  suggested_vendor_id: string | null;
  suggested_vendor_name: string | null;
  notes: string | null;
}

export interface RequisitionDetail extends Requisition {
  lines: RequisitionLine[];
}

export interface Allocation {
  id: string;
  boq_line_id: string;
  boq_ref: string;
  project_id: string;
  project_code: string;
  qty: string;
  received: string;
}

export interface PoLine {
  id: string;
  line_no: number;
  part_id: string;
  mpn: string;
  manufacturer: string | null;
  description: string;
  unit: string;
  msl_level: number | null;
  qty_ordered: string;
  unit_price: string | null;
  amount: string | null;
  expected_date: string | null;
  is_cancelled: boolean;
  notes: string | null;
  qty_accepted: string;
  qty_rejected: string;
  qty_on_hold: string;
  outstanding: string;
  allocations: Allocation[];
  row_version: number;
}

export type PoStatus = "draft" | "issued" | "partially_received" | "received" | "closed" | "cancelled";

export interface PurchaseOrder {
  id: string;
  number: string;
  vendor_id: string;
  vendor_code: string;
  vendor_name: string;
  requisition_id: string | null;
  requisition_number: string | null;
  status: PoStatus;
  order_date: string | null;
  issued_at: string | null;
  currency: string;
  notes: string | null;
  total: string;
  line_count: number;
  next_expected: string | null;
  project_codes: string[];
  created_at: string;
  row_version: number;
}

export interface PurchaseOrderDetail extends PurchaseOrder {
  lines: PoLine[];
  receipts: { id: string; number: string; received_at: string | null }[];
}

export interface PoLineInput {
  part_id: string;
  qty_ordered: string;
  unit_price: string | null;
  expected_date: string | null;
  notes: string | null;
  allocations: { boq_line_id: string; qty: string }[];
}

export interface GrnLine {
  id: string;
  po_line_id: string;
  po_line_no: number;
  part_id: string;
  mpn: string;
  description: string;
  location_id: string | null;
  location_code: string | null;
  qty_received: string;
  qty_accepted: string;
  qty_rejected: string;
  qty_on_hold: string;
  batch_lot: string | null;
  date_code: string | null;
  msl_level: number | null;
  inspection_result: "accept" | "reject" | "hold" | "partial";
  notes: string | null;
  allocated: Allocation[];
  row_version: number;
}

export interface Receipt {
  id: string;
  number: string;
  purchase_order_id: string;
  po_number: string;
  vendor_name: string;
  status: string;
  received_at: string | null;
  received_by_name: string | null;
  delivery_note_ref: string | null;
  coc_file_id: string | null;
  notes: string | null;
  qty_accepted: string;
  qty_rejected: string;
  qty_on_hold: string;
  row_version: number;
}

export interface VendorReturn {
  id: string;
  number: string;
  grn_id: string;
  grn_number: string;
  po_number: string;
  vendor_id: string;
  vendor_name: string;
  mpn: string;
  qty: string;
  reason: string;
  status: "open" | "shipped" | "credited" | "replaced" | "closed";
  created_at: string;
  row_version: number;
}

export interface ReceiptDetail extends Receipt {
  lines: GrnLine[];
  returns: VendorReturn[];
}

export interface GrnLineInput {
  po_line_id: string;
  location_id: string;
  qty_received: string;
  qty_accepted: string;
  qty_rejected: string;
  qty_on_hold: string;
  batch_lot: string | null;
  date_code: string | null;
  msl_level: number | null;
  reject_reason: string | null;
  notes: string | null;
}

export interface TrackerLine {
  boq_line_id: string;
  boq_id: string;
  boq_name: string;
  revision: string;
  module_id: string | null;
  module_code: string | null;
  line_no: number;
  ref_des: string | null;
  part_id: string | null;
  mpn: string | null;
  manufacturer: string | null;
  description: string | null;
  category: string | null;
  unit: string;
  dnp: boolean;
  required_qty: string;
  ordered_qty: string;
  received_qty: string;
  issued_qty: string;
  shortfall: string;
  pending_receipt: string;
  being_ordered: string;
  status: string;
  vendors: string[];
  purchase_orders: { po_id: string; po_number: string; vendor_name: string; expected_date: string | null; outstanding: string }[];
  expected_date: string | null;
  days_overdue: number;
  value_pending: string;
}

export interface Tracker {
  project_id: string;
  project_code: string;
  project_name: string;
  kpis: {
    lines: number;
    lines_required: number;
    pct_fully_received: number;
    lines_to_order: number;
    lines_awaiting_delivery: number;
    overdue_lines: number;
    value_pending: string;
  };
  modules: { module_id: string | null; module_code: string | null; module_name: string; lines: number; lines_received: number; clear_to_build: boolean; reason: string | null }[];
  lines: TrackerLine[];
  unreleased_boqs: string[];
}

export interface PendingLine {
  po_id: string;
  po_number: string;
  po_status: PoStatus;
  po_line_id: string;
  line_no: number;
  vendor_id: string;
  vendor_name: string;
  part_id: string;
  mpn: string;
  description: string;
  qty_ordered: string;
  qty_received: string;
  outstanding: string;
  unit_price: string | null;
  value_pending: string | null;
  expected_date: string | null;
  days_overdue: number;
  project_codes: string[];
  row_version: number;
}

/* ---------------------------------------------------------------- labels and tones */

export const PO_STATUS: Record<PoStatus, { label: string; tone: StatusTone }> = {
  draft: { label: "Draft", tone: "grey" },
  issued: { label: "Issued", tone: "blue" },
  partially_received: { label: "Partially received", tone: "amber" },
  received: { label: "Received", tone: "green" },
  closed: { label: "Closed", tone: "grey" },
  cancelled: { label: "Cancelled", tone: "red" },
};

export const PR_STATUS: Record<Requisition["status"], { label: string; tone: StatusTone }> = {
  draft: { label: "Draft", tone: "grey" },
  submitted: { label: "Awaiting approval", tone: "amber" },
  approved: { label: "Approved", tone: "blue" },
  rejected: { label: "Rejected", tone: "red" },
  converted: { label: "Ordered", tone: "green" },
};

export const RETURN_STATUS: Record<VendorReturn["status"], { label: string; tone: StatusTone }> = {
  open: { label: "Open", tone: "amber" },
  shipped: { label: "Shipped to vendor", tone: "blue" },
  credited: { label: "Credited", tone: "green" },
  replaced: { label: "Replaced", tone: "green" },
  closed: { label: "Closed", tone: "grey" },
};

export const INSPECTION: Record<GrnLine["inspection_result"], { label: string; tone: StatusTone }> = {
  accept: { label: "Accepted", tone: "green" },
  partial: { label: "Partly accepted", tone: "amber" },
  hold: { label: "On hold", tone: "amber" },
  reject: { label: "Rejected", tone: "red" },
};

/** Number formatting for quantities from the API (decimal strings). */
export const qty = (v: string | number | null | undefined) =>
  v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 4 });
export const money = (v: string | number | null | undefined) =>
  v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ---------------------------------------------------------------- queries */

export const procKeys = {
  all: ["procurement"] as const,
  vendors: (q = "") => ["procurement", "vendors", q] as const,
  prs: (filter: object) => ["procurement", "prs", filter] as const,
  pr: (id: string) => ["procurement", "pr", id] as const,
  pos: (filter: object) => ["procurement", "pos", filter] as const,
  po: (id: string) => ["procurement", "po", id] as const,
  grns: (poId?: string) => ["procurement", "grns", poId ?? ""] as const,
  grn: (id: string) => ["procurement", "grn", id] as const,
  returns: (status: string) => ["procurement", "returns", status] as const,
  tracker: (projectId: string) => ["procurement", "tracker", projectId] as const,
  pending: ["procurement", "pending"] as const,
};

export const useVendors = (q = "") =>
  useQuery({ queryKey: procKeys.vendors(q), queryFn: ({ signal }) => apiGet<Vendor[]>(`/vendors${qs({ q: q || null })}`, signal) });
export const useRequisitions = (filter: { project_id?: string; status?: string } = {}) =>
  useQuery({ queryKey: procKeys.prs(filter), queryFn: ({ signal }) => apiGet<Requisition[]>(`/requisitions${qs(filter)}`, signal) });
export const useRequisition = (id: string) =>
  useQuery({ queryKey: procKeys.pr(id), queryFn: ({ signal }) => apiGet<RequisitionDetail>(`/requisitions/${id}`, signal) });
export const useOrders = (filter: { status?: string; vendor_id?: string; project_id?: string; q?: string } = {}) =>
  useQuery({ queryKey: procKeys.pos(filter), queryFn: ({ signal }) => apiGet<PurchaseOrder[]>(`/purchase-orders${qs(filter)}`, signal) });
export const useOrder = (id: string | null) =>
  useQuery({ queryKey: procKeys.po(id ?? ""), queryFn: ({ signal }) => apiGet<PurchaseOrderDetail>(`/purchase-orders/${id}`, signal), enabled: !!id });
export const useReceipts = (poId?: string) =>
  useQuery({ queryKey: procKeys.grns(poId), queryFn: ({ signal }) => apiGet<Receipt[]>(`/goods-receipts${qs({ po_id: poId })}`, signal) });
export const useReceipt = (id: string) =>
  useQuery({ queryKey: procKeys.grn(id), queryFn: ({ signal }) => apiGet<ReceiptDetail>(`/goods-receipts/${id}`, signal) });
export const useReturns = (status = "") =>
  useQuery({ queryKey: procKeys.returns(status), queryFn: ({ signal }) => apiGet<VendorReturn[]>(`/vendor-returns${qs({ status: status || null })}`, signal) });
export const useTracker = (projectId: string | null) =>
  useQuery({ queryKey: procKeys.tracker(projectId ?? ""), queryFn: ({ signal }) => apiGet<Tracker>(`/projects/${projectId}/tracker`, signal), enabled: !!projectId });
export const usePending = () =>
  useQuery({ queryKey: procKeys.pending, queryFn: ({ signal }) => apiGet<PendingLine[]>("/procurement/pending", signal) });

/* ---------------------------------------------------------------- mutations */

export function useProcurementMutations() {
  const qc = useQueryClient();
  // Every procurement change can move tracker numbers, stock and BOQ statuses.
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: procKeys.all });
    void qc.invalidateQueries({ queryKey: ["inventory"] });
    void qc.invalidateQueries({ queryKey: ["boqs"] });
  };
  // Called in a fixed order on every render, like any hook.
  const useM = <A, R>(fn: (a: A) => Promise<R>) => useMutation({ mutationFn: fn, onSuccess: refresh });
  return {
    createVendor: useM((v: VendorInput) => apiPost<Vendor>("/vendors", v)),
    updateVendor: useM(({ id, ...v }: VendorInput & { id: string; row_version: number }) => apiPut<Vendor>(`/vendors/${id}`, v)),
    deleteVendor: useM(({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/vendors/${id}?row_version=${row_version}`)),
    raisePr: useM(({ projectId, boq_line_ids, notes }: { projectId: string; boq_line_ids: string[]; notes?: string | null }) =>
      apiPost<RequisitionDetail>(`/projects/${projectId}/requisitions`, { boq_line_ids, notes: notes ?? null }),
    ),
    updatePr: useM(({ id, ...b }: { id: string; row_version: number; notes: string | null; lines: { boq_line_id: string | null; part_id: string; qty: string; suggested_vendor_id: string | null; notes: string | null }[] }) =>
      apiPut<RequisitionDetail>(`/requisitions/${id}`, b),
    ),
    submitPr: useM(({ id, row_version }: { id: string; row_version: number }) => apiPost<RequisitionDetail>(`/requisitions/${id}/submit`, { row_version })),
    decidePr: useM(({ id, ...b }: { id: string; row_version: number; approve: boolean; note: string | null }) => apiPost<RequisitionDetail>(`/requisitions/${id}/decision`, b)),
    convertPr: useM(({ id, row_version }: { id: string; row_version: number }) => apiPost<PoRef[]>(`/requisitions/${id}/convert`, { row_version })),
    deletePr: useM(({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/requisitions/${id}?row_version=${row_version}`)),
    createPo: useM((b: { vendor_id: string; order_date: string | null; notes: string | null; lines: PoLineInput[] }) => apiPost<PurchaseOrderDetail>("/purchase-orders", b)),
    updatePo: useM(({ id, ...b }: { id: string; row_version: number; vendor_id: string; order_date: string | null; notes: string | null; lines: PoLineInput[] }) =>
      apiPut<PurchaseOrderDetail>(`/purchase-orders/${id}`, b),
    ),
    poAction: useM(({ id, action, row_version, note }: { id: string; action: "issue" | "cancel" | "close"; row_version: number; note?: string | null }) =>
      apiPost<PurchaseOrderDetail>(`/purchase-orders/${id}/${action}`, { row_version, note: note ?? null }),
    ),
    patchLine: useM(({ id, ...b }: { id: string; row_version: number; expected_date: string | null; notes: string | null }) => apiPatch<PurchaseOrderDetail>(`/po-lines/${id}`, b)),
    cancelLine: useM(({ id, row_version }: { id: string; row_version: number }) => apiPost<PurchaseOrderDetail>(`/po-lines/${id}/cancel`, { row_version })),
    receive: useM((b: { purchase_order_id: string; delivery_note_ref: string | null; notes: string | null; lines: GrnLineInput[] }) => apiPost<ReceiptDetail>("/goods-receipts", b)),
    patchReceipt: useM(({ id, ...b }: { id: string; row_version: number; coc_file_id: string | null; delivery_note_ref: string | null; notes: string | null }) =>
      apiPatch<ReceiptDetail>(`/goods-receipts/${id}`, b),
    ),
    resolveHold: useM(({ id, ...b }: { id: string; row_version: number; accept_qty: string; reject_qty: string; reason: string | null }) =>
      apiPost<ReceiptDetail>(`/grn-lines/${id}/resolve-hold`, b),
    ),
    updateReturn: useM(({ id, ...b }: { id: string; row_version: number; status: VendorReturn["status"]; note: string | null }) => apiPatch<VendorReturn>(`/vendor-returns/${id}`, b)),
  };
}

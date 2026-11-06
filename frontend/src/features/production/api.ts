import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { StatusTone } from "@/design/tokens";
import { apiDelete, apiGet, apiPost, apiPut, qs } from "@/lib/api";

export type WoStatus = "draft" | "released" | "in_progress" | "completed" | "closed" | "cancelled";
export type StageStatus = "not_started" | "in_progress" | "awaiting_qc" | "completed" | "blocked";

export interface TemplateStep {
  id?: string;
  seq?: number;
  stage_code: string;
  name: string;
  requires_qc: boolean;
}

export interface StageTemplate {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
  assembly_count: number;
  steps: TemplateStep[];
  row_version: number;
}

export interface StageSummary {
  id: string;
  seq: number;
  stage_code: string;
  name: string;
  requires_qc: boolean;
  status: StageStatus;
  units_in: number;
  units_done: number;
  units_failed: number;
  units_awaiting_qc: number;
}

export interface WorkOrder {
  id: string;
  number: string;
  project_id: string;
  project_code: string;
  project_name: string;
  module_id: string | null;
  module_code: string | null;
  assembly_id: string;
  assembly_label: string;
  boq_id: string | null;
  build_qty: number;
  status: WoStatus;
  planned_start: string | null;
  planned_end: string | null;
  released_at: string | null;
  release_override_reason: string | null;
  track_serials: boolean;
  notes: string | null;
  lot_id: string | null;
  lot_number: string | null;
  current_stage: string | null;
  units_completed: number;
  units_failed: number;
  serial_count: number;
  created_at: string;
  row_version: number;
}

export interface WorkOrderDetail extends WorkOrder {
  stages: StageSummary[];
  readiness: { clear_to_build: boolean; reason: string | null; lines: number; lines_received: number } | null;
}

export interface KitLine {
  boq_line_id: string;
  line_no: number;
  ref_des: string | null;
  part_id: string | null;
  mpn: string | null;
  description: string | null;
  unit: string;
  dnp: boolean;
  required: string;
  issued: string;
  shortage: string;
  available: string;
  reserved_for_project: string;
}

export interface Kit {
  boq_id: string | null;
  boq_name: string | null;
  revision: string | null;
  lines: KitLine[];
  complete: boolean;
}

export interface KitRecord {
  id: string;
  kind: "issue" | "return";
  boq_line_id: string;
  mpn: string;
  location_code: string;
  lot_code: string | null;
  qty: string;
  note: string | null;
  created_at: string;
  created_by_name: string | null;
}

export interface LotStock {
  location_id: string;
  location_code: string;
  lot_code: string | null;
  qty: string;
}

export interface Unit {
  id: string;
  serial_number: string;
  status: "in_production" | "passed" | "failed" | "rework" | "scrapped" | "shipped";
  current_stage: string | null;
  current_stage_id: string | null;
  current_stage_status: StageStatus | null;
}

export interface Progress {
  id: string;
  work_order_stage_id: string;
  stage_name: string;
  seq: number;
  serial_unit_id: string | null;
  serial_number: string | null;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
  qty_passed: number;
  qty_failed: number;
  operator_name: string | null;
  notes: string | null;
}

export interface Genealogy {
  serial_number: string;
  work_order_id: string;
  work_order_number: string;
  lot_number: string | null;
  assembly_label: string;
  parts: { boq_line_id: string; ref_des: string | null; mpn: string; lot_code: string | null; qty: string }[];
}

export interface ScanResult {
  serial_unit_id: string;
  serial_number: string;
  work_order_id: string;
  work_order_number: string;
  unit_status: Unit["status"];
  stage: Progress | null;
  stage_id: string | null;
  stage_name: string | null;
  stage_requires_qc: boolean;
  next_action: "start" | "finish" | "complete" | null;
}

export interface BoardCard {
  work_order_id: string;
  number: string;
  project_code: string;
  assembly_label: string;
  build_qty: number;
  status: WoStatus;
  stage_name: string | null;
  stage_seq: number | null;
  stage_count: number;
  units_at_stage: number;
  units_done_at_stage: number;
  awaiting_qc: number;
  planned_end: string | null;
}

export interface BoardColumn {
  key: string;
  label: string;
  cards: BoardCard[];
}

export const STAGE_CODES: { value: string; label: string }[] = [
  { value: "kitting", label: "Kitting" },
  { value: "smt", label: "SMT placement" },
  { value: "reflow", label: "Reflow" },
  { value: "aoi", label: "AOI" },
  { value: "tht", label: "THT insertion" },
  { value: "wave_solder", label: "Wave solder" },
  { value: "hand_solder", label: "Hand solder" },
  { value: "cleaning", label: "Cleaning" },
  { value: "conformal_coat", label: "Conformal coat" },
  { value: "programming", label: "Programming" },
  { value: "functional_test", label: "Functional test" },
  { value: "final_assembly", label: "Final assembly" },
  { value: "packing", label: "Packing" },
  { value: "custom", label: "Custom" },
];

export const WO_STATUS: Record<WoStatus, { label: string; tone: StatusTone }> = {
  draft: { label: "Planned", tone: "grey" },
  released: { label: "Released", tone: "blue" },
  in_progress: { label: "In progress", tone: "blue" },
  completed: { label: "Completed", tone: "green" },
  closed: { label: "Closed", tone: "grey" },
  cancelled: { label: "Cancelled", tone: "red" },
};

export const STAGE_STATUS: Record<StageStatus, { label: string; tone: StatusTone }> = {
  not_started: { label: "Not started", tone: "grey" },
  in_progress: { label: "In progress", tone: "blue" },
  awaiting_qc: { label: "Awaiting QC", tone: "amber" },
  completed: { label: "Completed", tone: "green" },
  blocked: { label: "Blocked", tone: "red" },
};

export const UNIT_STATUS: Record<Unit["status"], { label: string; tone: StatusTone }> = {
  in_production: { label: "In production", tone: "blue" },
  passed: { label: "Passed", tone: "green" },
  failed: { label: "Failed", tone: "red" },
  rework: { label: "Rework", tone: "amber" },
  scrapped: { label: "Scrapped", tone: "red" },
  shipped: { label: "Shipped", tone: "green" },
};

export const prodKeys = {
  all: ["production"] as const,
  templates: ["production", "templates"] as const,
  wos: (f: object) => ["production", "wos", f] as const,
  wo: (id: string) => ["production", "wo", id] as const,
  kit: (id: string) => ["production", "kit", id] as const,
  records: (id: string) => ["production", "records", id] as const,
  units: (id: string) => ["production", "units", id] as const,
  progress: (id: string) => ["production", "progress", id] as const,
  board: ["production", "board"] as const,
  lots: (partId: string) => ["inventory", "lots", partId] as const,
};

export const useTemplates = () =>
  useQuery({ queryKey: prodKeys.templates, queryFn: ({ signal }) => apiGet<StageTemplate[]>("/production/stage-templates", signal) });
export const useWorkOrders = (f: { project_id?: string; status?: string } = {}) =>
  useQuery({ queryKey: prodKeys.wos(f), queryFn: ({ signal }) => apiGet<WorkOrder[]>(`/work-orders${qs(f)}`, signal) });
export const useWorkOrder = (id: string) =>
  useQuery({ queryKey: prodKeys.wo(id), queryFn: ({ signal }) => apiGet<WorkOrderDetail>(`/work-orders/${id}`, signal) });
export const useKit = (id: string, enabled = true) =>
  useQuery({ queryKey: prodKeys.kit(id), queryFn: ({ signal }) => apiGet<Kit>(`/work-orders/${id}/kit`, signal), enabled });
export const useKitRecords = (id: string, enabled = true) =>
  useQuery({ queryKey: prodKeys.records(id), queryFn: ({ signal }) => apiGet<KitRecord[]>(`/work-orders/${id}/kit/records`, signal), enabled });
export const useUnits = (id: string, enabled = true) =>
  useQuery({ queryKey: prodKeys.units(id), queryFn: ({ signal }) => apiGet<Unit[]>(`/work-orders/${id}/units`, signal), enabled });
export const useProgress = (id: string, enabled = true) =>
  useQuery({ queryKey: prodKeys.progress(id), queryFn: ({ signal }) => apiGet<Progress[]>(`/work-orders/${id}/progress`, signal), enabled });
export const useBoard = () => useQuery({ queryKey: prodKeys.board, queryFn: ({ signal }) => apiGet<BoardColumn[]>("/production/board", signal) });
export const useLots = (partId: string | null) =>
  useQuery({ queryKey: prodKeys.lots(partId ?? ""), queryFn: ({ signal }) => apiGet<LotStock[]>(`/inventory/lots${qs({ part_id: partId })}`, signal), enabled: !!partId });

export const scanSerial = (code: string) => apiGet<ScanResult>(`/production/scan${qs({ code })}`);
export const fetchGenealogy = (unitId: string) => apiGet<Genealogy>(`/serial-units/${unitId}/genealogy`);

export function useProductionMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: prodKeys.all });
    void qc.invalidateQueries({ queryKey: ["inventory"] });
    void qc.invalidateQueries({ queryKey: ["procurement"] });
  };
  // Called in a fixed order on every render, like any hook.
  const useM = <A, R>(fn: (a: A) => Promise<R>) => useMutation({ mutationFn: fn, onSuccess: refresh });
  return {
    createTemplate: useM((b: { name: string; description: string | null; copy_from_id: string | null }) => apiPost<StageTemplate>("/stage-templates", b)),
    updateTemplate: useM(({ id, ...b }: { id: string; row_version: number; name: string; description: string | null; steps: TemplateStep[] }) =>
      apiPut<StageTemplate>(`/stage-templates/${id}`, b),
    ),
    deleteTemplate: useM(({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/stage-templates/${id}?row_version=${row_version}`)),
    createWo: useM((b: { assembly_id: string; build_qty: number; planned_start: string | null; planned_end: string | null; track_serials: boolean; boq_id: string | null; notes: string | null }) =>
      apiPost<WorkOrderDetail>("/work-orders", b),
    ),
    updateWo: useM(({ id, ...b }: { id: string; row_version: number; build_qty: number; planned_start: string | null; planned_end: string | null; track_serials: boolean; boq_id: string | null; notes: string | null }) =>
      apiPut<WorkOrderDetail>(`/work-orders/${id}`, b),
    ),
    release: useM(({ id, ...b }: { id: string; row_version: number; override_reason: string | null }) => apiPost<WorkOrderDetail>(`/work-orders/${id}/release`, b)),
    woAction: useM(({ id, action, row_version }: { id: string; action: "cancel" | "close"; row_version: number }) => apiPost<WorkOrderDetail>(`/work-orders/${id}/${action}`, { row_version })),
    issue: useM(({ id, issues }: { id: string; issues: { boq_line_id: string; location_id: string; qty: string; lot_code: string | null; note: string | null }[] }) =>
      apiPost<KitRecord[]>(`/work-orders/${id}/kit/issue`, { issues }),
    ),
    returnParts: useM(({ id, ...b }: { id: string; boq_line_id: string; location_id: string; qty: string; lot_code: string | null; note: string | null }) =>
      apiPost<KitRecord>(`/work-orders/${id}/kit/return`, b),
    ),
    serials: useM(({ id, count }: { id: string; count: number | null }) => apiPost<Unit[]>(`/work-orders/${id}/serials`, { count })),
    progress: useM(({ stageId, ...b }: { stageId: string; action: "start" | "finish" | "complete"; serial_unit_id?: string | null; qty_passed?: number | null; qty_failed?: number | null; passed?: boolean | null; notes?: string | null }) =>
      apiPost<Progress>(`/work-order-stages/${stageId}/progress`, b),
    ),
  };
}

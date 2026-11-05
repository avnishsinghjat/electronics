import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { StatusTone } from "@/design/tokens";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, qs } from "@/lib/api";

export interface RevisionSummary {
  id: string;
  revision: string;
  status: "draft" | "released" | "superseded";
  build_qty: number;
  line_count: number;
  released_at: string | null;
  created_at: string;
  row_version: number;
}

export interface Boq {
  id: string;
  project_id: string;
  project_code: string;
  project_name: string;
  module_id: string | null;
  module_code: string | null;
  assembly_id: string | null;
  assembly_label: string | null;
  name: string;
  notes: string | null;
  row_version: number;
  revisions: RevisionSummary[];
}

export interface BoqLine {
  id: string;
  line_key: string;
  line_no: number;
  part_id: string | null;
  ref_des: string | null;
  qty_per_unit: string;
  mpn: string | null;
  manufacturer: string | null;
  description: string | null;
  value: string | null;
  package: string | null;
  category: string | null;
  unit: string;
  dnp: boolean;
  attrition_pct: string;
  attrition_override: boolean;
  unit_price: string | null;
  preferred_vendor_id: string | null;
  notes: string | null;
  required_qty: string;
  ordered_qty: string;
  received_qty: string;
  issued_qty: string;
  shortfall: string;
  pending_receipt: string;
  status: string;
}

export interface RevisionDetail {
  id: string;
  boq_id: string;
  revision: string;
  status: RevisionSummary["status"];
  build_qty: number;
  attrition_by_category: Record<string, number>;
  released_at: string | null;
  notes: string | null;
  row_version: number;
  lines: BoqLine[];
}

export interface LineInput {
  line_key: string | null;
  part_id: string | null;
  ref_des: string | null;
  qty_per_unit: string;
  mpn: string | null;
  manufacturer: string | null;
  description: string | null;
  value: string | null;
  package: string | null;
  category: string | null;
  unit: string;
  dnp: boolean;
  attrition_pct: string | null;
  unit_price: string | null;
  notes: string | null;
}

export interface Issue {
  row: number;
  field: string | null;
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
}

export interface ImportLine {
  rows: number[];
  ref_des: string[];
  qty_per_unit: string;
  mpn: string | null;
  manufacturer: string | null;
  description: string | null;
  category: string | null;
  unit: string;
  dnp: boolean;
  part_known: boolean;
}

export interface ImportSession {
  id: string;
  boq_id: string;
  file_id: string;
  file_name: string;
  status: "uploaded" | "parsing" | "parsed" | "validating" | "validated" | "committed" | "failed";
  encoding: string | null;
  delimiter: string | null;
  sheet: string | null;
  header_row: number | null;
  headers: string[] | null;
  preview_rows: string[][];
  total_rows: number;
  mapping: Record<string, number> | null;
  suggested_template_id: string | null;
  result: { lines: ImportLine[]; issues: Issue[]; source_rows: number; stats: Record<string, number> } | null;
  error: string | null;
  revision_id: string | null;
  row_version: number;
}

export interface FieldInfo {
  field: string;
  label: string;
}

export interface MappingTemplate {
  id: string;
  name: string;
  client_name: string | null;
  mapping: Record<string, string>;
  row_version: number;
}

export interface DiffLine {
  line_key: string;
  change: "added" | "removed" | "qty_changed" | "substituted" | "changed" | "unchanged";
  from_line: Record<string, string | boolean | number | null> | null;
  to_line: Record<string, string | boolean | number | null> | null;
  changed_fields: string[];
}

export interface Comparison {
  boq_id: string;
  from_revision: string;
  to_revision: string;
  summary: Record<DiffLine["change"], number>;
  lines: DiffLine[];
}

export interface PartHit {
  id: string;
  mpn: string;
  manufacturer: string | null;
  description: string;
  package: string | null;
  value: string | null;
  category: string;
  unit: string;
}

export const REVISION_TONE: Record<RevisionSummary["status"], StatusTone> = { draft: "amber", released: "green", superseded: "grey" };

/** Tones for the status strings computed by the server's status service. */
export const LINE_STATUS_TONE: Record<string, StatusTone> = {
  "Not required": "grey",
  "Not ordered": "grey",
  "Partially ordered": "amber",
  Ordered: "blue",
  "Partially received": "amber",
  Received: "green",
  Issued: "green",
};

export const CATEGORIES = ["Passive", "IC", "Discrete", "Connector", "Electromechanical", "Magnetics", "Opto", "Crystal", "Mechanical", "PCB", "Consumable", "Other"];

export const boqKeys = {
  all: ["boqs"] as const,
  project: (id: string) => ["boqs", "project", id] as const,
  revision: (id: string) => ["boqs", "revision", id] as const,
  imp: (id: string) => ["boqs", "import", id] as const,
  compare: (id: string, a: string, b: string) => ["boqs", "compare", id, a, b] as const,
  fields: ["boqs", "fields"] as const,
  templates: ["boqs", "templates"] as const,
};

export const useAllBoqs = () => useQuery({ queryKey: boqKeys.all, queryFn: ({ signal }) => apiGet<Boq[]>("/boqs", signal) });
export const useProjectBoqs = (projectId: string) =>
  useQuery({ queryKey: boqKeys.project(projectId), queryFn: ({ signal }) => apiGet<Boq[]>(`/projects/${projectId}/boqs`, signal) });
export const useRevision = (id: string | null) =>
  useQuery({ queryKey: boqKeys.revision(id ?? ""), queryFn: ({ signal }) => apiGet<RevisionDetail>(`/boq-revisions/${id}`, signal), enabled: !!id });
export const useImportFields = () => useQuery({ queryKey: boqKeys.fields, queryFn: ({ signal }) => apiGet<FieldInfo[]>("/boq-import-fields", signal), staleTime: Infinity });
export const useTemplates = () => useQuery({ queryKey: boqKeys.templates, queryFn: ({ signal }) => apiGet<MappingTemplate[]>("/boq-mapping-templates", signal) });

const BUSY = new Set(["uploaded", "parsing", "validating"]);
export const useImportSession = (id: string | null) =>
  useQuery({
    queryKey: boqKeys.imp(id ?? ""),
    queryFn: ({ signal }) => apiGet<ImportSession>(`/boq-imports/${id}`, signal),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? 700 : false),
  });

export const useComparison = (boqId: string, from: string | null, to: string | null) =>
  useQuery({
    queryKey: boqKeys.compare(boqId, from ?? "", to ?? ""),
    queryFn: ({ signal }) => apiGet<Comparison>(`/boqs/${boqId}/compare${qs({ from, to })}`, signal),
    enabled: !!from && !!to && from !== to,
  });

export async function searchParts(q: string, signal: AbortSignal): Promise<PartHit[]> {
  return apiGet<PartHit[]>(`/parts${qs({ q, limit: 15 })}`, signal);
}

export function useBoqMutations(projectId: string) {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: boqKeys.all });
  return {
    createBoq: useMutation({
      mutationFn: (b: { name: string; module_id: string | null; assembly_id: string | null; build_qty: number | null; create_revision: boolean }) =>
        apiPost<Boq>(`/projects/${projectId}/boqs`, b),
      onSuccess: refresh,
    }),
    deleteBoq: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/boqs/${id}?row_version=${row_version}`), onSuccess: refresh }),
    newRevision: useMutation({ mutationFn: (boqId: string) => apiPost<RevisionSummary>(`/boqs/${boqId}/revisions`), onSuccess: refresh }),
    deleteRevision: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/boq-revisions/${id}?row_version=${row_version}`), onSuccess: refresh }),
    release: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiPost<RevisionSummary>(`/boq-revisions/${id}/release`, { row_version }), onSuccess: refresh }),
    updateBuild: useMutation({
      mutationFn: ({ id, ...b }: { id: string; row_version: number; build_qty?: number; attrition_by_category?: Record<string, number> }) =>
        apiPatch<RevisionSummary>(`/boq-revisions/${id}`, b),
      onSuccess: refresh,
    }),
    saveLines: useMutation({
      mutationFn: ({ id, row_version, lines }: { id: string; row_version: number; lines: LineInput[] }) =>
        apiPut<RevisionSummary>(`/boq-revisions/${id}/lines`, { row_version, lines }),
      onSuccess: refresh,
    }),
  };
}

export function useImportMutations() {
  const qc = useQueryClient();
  return {
    upload: useMutation({
      mutationFn: ({ boqId, file }: { boqId: string; file: File }) => {
        const body = new FormData();
        body.append("file", file);
        return apiPost<ImportSession>(`/boqs/${boqId}/imports`, body);
      },
    }),
    setMapping: useMutation({
      mutationFn: ({ id, ...b }: { id: string; row_version: number; header_row: number; mapping: Record<string, number>; decimal_comma: boolean; save_template_name: string | null; template_client: string | null }) =>
        apiPut<ImportSession>(`/boq-imports/${id}/mapping`, b),
      onSuccess: (data) => {
        qc.setQueryData(boqKeys.imp(data.id), data);
        void qc.invalidateQueries({ queryKey: boqKeys.templates });
      },
    }),
    commit: useMutation({
      mutationFn: ({ id, ...b }: { id: string; row_version: number; release: boolean; build_qty: number | null }) =>
        apiPost<RevisionSummary>(`/boq-imports/${id}/commit`, b),
      onSuccess: () => void qc.invalidateQueries({ queryKey: boqKeys.all }),
    }),
  };
}

export async function templateMapping(importId: string, templateId: string): Promise<Record<string, number>> {
  return apiGet<Record<string, number>>(`/boq-imports/${importId}/template/${templateId}`);
}

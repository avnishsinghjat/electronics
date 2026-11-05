import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { StatusTone } from "@/design/tokens";
import { apiDelete, apiGet, apiPatch, apiPost, qs } from "@/lib/api";

export type ProjectStatus = "draft" | "active" | "on_hold" | "completed" | "cancelled";

export const PROJECT_STATUSES: { value: ProjectStatus; label: string; tone: StatusTone }[] = [
  { value: "draft", label: "Draft", tone: "grey" },
  { value: "active", label: "Active", tone: "blue" },
  { value: "on_hold", label: "On hold", tone: "amber" },
  { value: "completed", label: "Completed", tone: "green" },
  { value: "cancelled", label: "Cancelled", tone: "grey" },
];

export function statusInfo(status: string) {
  return PROJECT_STATUSES.find((s) => s.value === status) ?? { value: status, label: status, tone: "grey" as StatusTone };
}

export interface Division {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_sample: boolean;
  row_version: number;
}

export interface Project {
  id: string;
  division_id: string;
  code: string;
  name: string;
  client_name: string;
  client_po_ref: string | null;
  start_date: string | null;
  due_date: string | null;
  status: ProjectStatus;
  project_manager_id: string | null;
  notes: string | null;
  is_sample: boolean;
  row_version: number;
  created_at: string;
  updated_at: string;
  division_code: string;
  division_name: string;
  project_manager_name: string | null;
  module_count: number;
}

export interface Module {
  id: string;
  project_id: string;
  code: string;
  name: string;
  qty_to_deliver: number;
  description: string | null;
  row_version: number;
}

export interface Assembly {
  id: string;
  module_id: string;
  code: string;
  board_name: string;
  revision: string;
  qty_per_module: number;
  layer_count: number;
  size_x_mm: string | null;
  size_y_mm: string | null;
  finish: string | null;
  kicad_project_file_id: string | null;
  assembly_drawing_file_id: string | null;
  stage_template_id: string | null;
  notes: string | null;
  row_version: number;
}

export interface ProjectTree {
  project: Project;
  modules: (Module & { assemblies: Assembly[] })[];
}

export interface HistoryEntry {
  id: number;
  occurred_at: string;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  label: string;
  changed_fields: string[] | null;
}

export interface StaffMember {
  id: string;
  username: string;
  full_name: string;
  roles: string[];
}

export interface StageTemplate {
  id: string;
  name: string;
  is_default: boolean;
}

export interface ProjectFilters {
  status?: string;
  division_id?: string;
  project_manager_id?: string;
  client?: string;
  q?: string;
  due_after?: string;
  due_before?: string;
  overdue?: boolean;
}

interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const projectKeys = {
  divisions: ["divisions"] as const,
  list: (f: ProjectFilters) => ["projects", "list", f] as const,
  tree: (id: string) => ["projects", "tree", id] as const,
  history: (id: string) => ["projects", "history", id] as const,
  staff: ["directory", "users"] as const,
  templates: ["stage-templates"] as const,
};

export const useDivisionsQuery = () =>
  useQuery({ queryKey: projectKeys.divisions, queryFn: ({ signal }) => apiGet<Division[]>("/divisions", signal), staleTime: 60_000 });

export const useProjects = (f: ProjectFilters) =>
  useQuery({
    queryKey: projectKeys.list(f),
    queryFn: ({ signal }) => apiGet<Page<Project>>(`/projects${qs({ ...f, page_size: 500, sort: "due_date" })}`, signal),
    placeholderData: keepPreviousData,
  });

export const useProjectTree = (id: string) =>
  useQuery({ queryKey: projectKeys.tree(id), queryFn: ({ signal }) => apiGet<ProjectTree>(`/projects/${id}/tree`, signal) });

export const useProjectHistory = (id: string, enabled: boolean) =>
  useQuery({ queryKey: projectKeys.history(id), queryFn: ({ signal }) => apiGet<HistoryEntry[]>(`/projects/${id}/history`, signal), enabled });

export const useStaff = (enabled = true) =>
  useQuery({ queryKey: projectKeys.staff, queryFn: ({ signal }) => apiGet<StaffMember[]>("/directory/users", signal), enabled, staleTime: 60_000 });

export const useStageTemplates = () =>
  useQuery({ queryKey: projectKeys.templates, queryFn: ({ signal }) => apiGet<StageTemplate[]>("/stage-templates", signal), staleTime: Infinity });

export async function searchProjectsForSwitcher(q: string, signal: AbortSignal) {
  return (await apiGet<Page<Project>>(`/projects${qs({ q, page_size: 15, sort: "-created_at" })}`, signal)).items;
}

export type ProjectInput = {
  division_id: string;
  name: string;
  client_name: string;
  client_po_ref: string | null;
  start_date: string | null;
  due_date: string | null;
  status: ProjectStatus;
  project_manager_id: string | null;
  notes: string | null;
};

export type ModuleInput = { code: string; name: string; qty_to_deliver: number; description: string | null };

export type AssemblyInput = {
  code: string;
  board_name: string;
  revision: string;
  qty_per_module: number;
  layer_count: number;
  size_x_mm: string | null;
  size_y_mm: string | null;
  finish: string | null;
  stage_template_id: string | null;
  notes: string | null;
  assembly_drawing_file_id?: string | null;
  kicad_project_file_id?: string | null;
};

export function useOrgMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["projects"] });
    void qc.invalidateQueries({ queryKey: projectKeys.divisions });
  };
  return {
    createDivision: useMutation({ mutationFn: (b: { code: string; name: string; description: string | null }) => apiPost<Division>("/divisions", b), onSuccess: refresh }),
    updateDivision: useMutation({
      mutationFn: ({ id, ...b }: { id: string; row_version: number; code: string; name: string; description: string | null }) => apiPatch<Division>(`/divisions/${id}`, b),
      onSuccess: refresh,
    }),
    deleteDivision: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/divisions/${id}?row_version=${row_version}`), onSuccess: refresh }),
    createProject: useMutation({ mutationFn: (b: ProjectInput) => apiPost<Project>("/projects", b), onSuccess: refresh }),
    updateProject: useMutation({
      mutationFn: ({ id, ...b }: Partial<ProjectInput> & { id: string; row_version: number }) => apiPatch<Project>(`/projects/${id}`, b),
      onSuccess: refresh,
    }),
    deleteProject: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/projects/${id}?row_version=${row_version}`), onSuccess: refresh }),
    cloneProject: useMutation({
      mutationFn: ({ id, ...b }: { id: string; name: string; client_po_ref: string | null; start_date: string | null; due_date: string | null; include_boq: boolean }) =>
        apiPost<Project>(`/projects/${id}/clone`, b),
      onSuccess: refresh,
    }),
    createModule: useMutation({ mutationFn: ({ projectId, ...b }: ModuleInput & { projectId: string }) => apiPost<Module>(`/projects/${projectId}/modules`, b), onSuccess: refresh }),
    updateModule: useMutation({ mutationFn: ({ id, ...b }: Partial<ModuleInput> & { id: string; row_version: number }) => apiPatch<Module>(`/modules/${id}`, b), onSuccess: refresh }),
    deleteModule: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/modules/${id}?row_version=${row_version}`), onSuccess: refresh }),
    createAssembly: useMutation({ mutationFn: ({ moduleId, ...b }: AssemblyInput & { moduleId: string }) => apiPost<Assembly>(`/modules/${moduleId}/assemblies`, b), onSuccess: refresh }),
    updateAssembly: useMutation({ mutationFn: ({ id, ...b }: Partial<AssemblyInput> & { id: string; row_version: number }) => apiPatch<Assembly>(`/assemblies/${id}`, b), onSuccess: refresh }),
    deleteAssembly: useMutation({ mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiDelete(`/assemblies/${id}?row_version=${row_version}`), onSuccess: refresh }),
  };
}

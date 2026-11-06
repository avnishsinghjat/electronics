import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Numbering, Role, Scope } from "@/features/auth/types";
import { apiGet, apiPost, apiPut, apiPatch, qs } from "@/lib/api";

export interface Company {
  company_name: string;
  address: string | null;
  gstin: string | null;
  serial_prefix: string;
  has_logo: boolean;
  row_version: number;
}

export interface UserRow {
  id: string;
  username: string;
  full_name: string;
  email: string | null;
  is_active: boolean;
  must_change_password: boolean;
  locked_until: string | null;
  last_login_at: string | null;
  roles: Role[];
  scopes: Scope[];
  row_version: number;
  created_at: string;
}

export interface UserWithPassword {
  user: UserRow;
  temporary_password: string;
}

export interface RoleInfo {
  role: Role;
  label: string;
  permissions: string[];
}

export interface AuditEntry {
  id: number;
  occurred_at: string;
  actor_id: string | null;
  actor_username: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  changed_fields: string[] | null;
  request_id: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DivisionRow {
  id: string;
  code: string;
  name: string;
}

export interface ProjectRow {
  id: string;
  code: string;
  name: string;
  division_id: string;
  client_name: string;
  status: string;
}

export const keys = {
  company: ["settings", "company"] as const,
  numbering: ["settings", "numbering"] as const,
  users: ["users"] as const,
  roles: ["users", "roles"] as const,
  audit: (f: object) => ["audit", f] as const,
  auditTypes: ["audit", "entity-types"] as const,
  divisions: ["divisions"] as const,
};

export const useCompany = () => useQuery({ queryKey: keys.company, queryFn: ({ signal }) => apiGet<Company>("/settings/company", signal) });
export const useNumbering = () => useQuery({ queryKey: keys.numbering, queryFn: ({ signal }) => apiGet<Numbering[]>("/settings/numbering", signal) });
export const useUsers = () =>
  useQuery({ queryKey: keys.users, queryFn: ({ signal }) => apiGet<Page<UserRow>>("/users?page_size=500", signal) });
export const useRoles = () => useQuery({ queryKey: keys.roles, queryFn: ({ signal }) => apiGet<RoleInfo[]>("/users/roles", signal), staleTime: Infinity });
export const useDivisions = () => useQuery({ queryKey: keys.divisions, queryFn: ({ signal }) => apiGet<DivisionRow[]>("/divisions", signal) });

export interface AuditFilters {
  actor_id?: string;
  entity_type?: string;
  entity_id?: string;
  action?: string;
  date_from?: string;
  date_to?: string;
  page: number;
  page_size: number;
}

export const useAudit = (f: AuditFilters) =>
  useQuery({
    queryKey: keys.audit(f),
    queryFn: ({ signal }) => apiGet<Page<AuditEntry>>(`/audit${qs({ ...f })}`, signal),
    placeholderData: (prev) => prev,
  });
export const useAuditTypes = () => useQuery({ queryKey: keys.auditTypes, queryFn: ({ signal }) => apiGet<string[]>("/audit/entity-types", signal) });

export async function searchProjects(q: string, signal: AbortSignal): Promise<ProjectRow[]> {
  return (await apiGet<Page<ProjectRow>>(`/projects${qs({ q, page_size: 20, sort: "name" })}`, signal)).items;
}

export function useSaveCompany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Omit<Company, "has_logo">) => apiPut<Company>("/settings/company", body),
    onSuccess: (data) => {
      qc.setQueryData(keys.company, data);
      void qc.invalidateQueries({ queryKey: ["branding"] });
    },
  });
}

export function useSavePrefix() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ doc_type, prefix }: { doc_type: string; prefix: string }) => apiPut<Numbering>(`/settings/numbering/${doc_type}`, { prefix }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.numbering }),
  });
}

export function useUploadLogo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiPost<{ id: string; sha256: string }>("/settings/logo", body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["branding"] });
      void qc.invalidateQueries({ queryKey: keys.company });
    },
  });
}

export interface UserInput {
  username: string;
  full_name: string;
  email: string | null;
  roles: Role[];
  scopes: Scope[];
}

export function useUserMutations() {
  const qc = useQueryClient();
  const done = () => void qc.invalidateQueries({ queryKey: keys.users });
  return {
    create: useMutation({ mutationFn: (body: UserInput) => apiPost<UserWithPassword>("/users", body), onSuccess: done }),
    update: useMutation({
      mutationFn: ({ id, ...body }: Partial<UserInput> & { id: string; row_version: number }) => apiPatch<UserRow>(`/users/${id}`, body),
      onSuccess: done,
    }),
    reset: useMutation({
      mutationFn: ({ id, row_version }: { id: string; row_version: number }) => apiPost<UserWithPassword>(`/users/${id}/reset-password`, { row_version }),
      onSuccess: done,
    }),
    setActive: useMutation({
      mutationFn: ({ id, row_version, active }: { id: string; row_version: number; active: boolean }) =>
        apiPost<UserRow>(`/users/${id}/${active ? "activate" : "deactivate"}`, { row_version }),
      onSuccess: done,
    }),
  };
}

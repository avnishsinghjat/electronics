import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Combobox, type ComboboxOption, Select } from "@/design/components";
import { useAuth } from "@/features/auth/AuthContext";
import { useCurrentDivision } from "@/features/projects/DivisionContext";
import { searchProjectsForSwitcher, useDivisionsQuery } from "@/features/projects/api";

const ALL = "__all";

/** Top-bar division filter. Applies to project lists and (Phase 13) dashboards. */
export function DivisionSwitcher() {
  const { divisionId, setDivisionId } = useCurrentDivision();
  const divisions = useDivisionsQuery();
  const known = divisions.data?.some((d) => d.id === divisionId);
  React.useEffect(() => {
    // A remembered division that no longer exists (or left the user's scope) resets.
    if (divisions.data && divisionId && !known) setDivisionId(null);
  }, [divisions.data, divisionId, known, setDivisionId]);
  if (!divisions.data || divisions.data.length < 2) return null;
  return (
    <Select
      aria-label="Division"
      className="h-8 w-48 text-xs"
      value={divisionId && known ? divisionId : ALL}
      onValueChange={(v) => setDivisionId(v === ALL ? null : v)}
      options={[{ value: ALL, label: "All divisions" }, ...divisions.data.map((d) => ({ value: d.id, label: d.name }))]}
    />
  );
}

/** Jump to any project in scope by code, name or client. */
export function ProjectSwitcher() {
  const navigate = useNavigate();
  const load = React.useCallback(
    async (q: string, signal: AbortSignal): Promise<ComboboxOption[]> =>
      (await searchProjectsForSwitcher(q, signal)).map((p) => ({ value: p.id, label: `${p.code} · ${p.name}`, description: p.client_name })),
    [],
  );
  return (
    <Combobox
      aria-label="Jump to project"
      className="h-8 w-56 text-xs"
      value={null}
      placeholder="Jump to project…"
      searchPlaceholder="Code, name or client"
      loadOptions={load}
      onChange={(opt) => opt && navigate(`/projects/${opt.value}`)}
    />
  );
}

export function useShowSwitchers(): boolean {
  return useAuth().can("projects:read");
}

import type { ColumnDef } from "@tanstack/react-table";
import { format } from "date-fns";
import { ChevronLeft, ChevronRight, History, RotateCcw } from "lucide-react";
import * as React from "react";

import { Badge, Button, DataTable, DatePicker, Drawer, DrawerContent, EmptyState, Field, MonoText, Select, StatusPill } from "@/design/components";
import type { StatusTone } from "@/design/tokens";
import { cn } from "@/lib/utils";

import { type AuditEntry, type AuditFilters, useAudit, useAuditTypes, useUsers } from "./api";

const PAGE_SIZE = 100;
const ALL = "__all";

const ACTION_TONE: Record<string, StatusTone> = {
  insert: "green",
  update: "blue",
  soft_delete: "amber",
  restore: "blue",
  delete: "red",
  login: "grey",
  login_failed: "amber",
  locked: "red",
  logout: "grey",
};

const ACTION_LABEL: Record<string, string> = {
  insert: "Created",
  update: "Updated",
  soft_delete: "Deleted",
  restore: "Restored",
  delete: "Removed",
  login: "Signed in",
  login_failed: "Failed sign-in",
  locked: "Account locked",
  logout: "Signed out",
};

const HIDDEN_FIELDS = new Set(["updated_at", "updated_by", "row_version"]);

function display(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Field-by-field before/after table; changed fields are highlighted and listed first. */
export function AuditDiff({ entry }: { entry: AuditEntry }) {
  const changed = new Set(entry.changed_fields ?? []);
  const keys = Array.from(new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]))
    .filter((k) => !HIDDEN_FIELDS.has(k) || changed.has(k))
    .sort((a, b) => Number(changed.has(b)) - Number(changed.has(a)) || a.localeCompare(b));
  if (keys.length === 0) return <p className="text-sm text-neutral-500">No field data recorded for this event.</p>;
  return (
    <table className="w-full table-fixed text-sm" aria-label="Field changes">
      <thead className="text-left text-xs font-semibold text-neutral-600">
        <tr className="border-b">
          <th scope="col" className="w-1/4 py-2 pr-2">Field</th>
          <th scope="col" className="py-2 pr-2">Before</th>
          <th scope="col" className="py-2">After</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => {
          const isChanged = changed.has(k);
          return (
            <tr key={k} className={cn("border-b border-neutral-100 align-top", isChanged && "bg-status-amber-bg/60")} data-changed={isChanged || undefined}>
              <th scope="row" className="py-1.5 pr-2 text-left font-mono text-xs font-normal text-neutral-600">{k}</th>
              <td className={cn("break-words py-1.5 pr-2 font-mono text-xs", isChanged ? "text-status-red-fg line-through decoration-status-red-dot/40" : "text-neutral-700")}>
                {entry.before ? display(entry.before[k]) : "—"}
              </td>
              <td className={cn("break-words py-1.5 font-mono text-xs", isChanged ? "font-semibold text-status-green-fg" : "text-neutral-700")}>
                {entry.after ? display(entry.after[k]) : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function AuditLogPage() {
  const users = useUsers();
  const types = useAuditTypes();
  const [filters, setFilters] = React.useState<AuditFilters>({ page: 1, page_size: PAGE_SIZE });
  const [from, setFrom] = React.useState<Date | null>(null);
  const [to, setTo] = React.useState<Date | null>(null);
  const [selected, setSelected] = React.useState<AuditEntry | null>(null);
  const audit = useAudit(filters);

  const set = (patch: Partial<AuditFilters>) => setFilters((f) => ({ ...f, ...patch, page: 1 }));
  const pages = audit.data ? Math.max(1, Math.ceil(audit.data.total / PAGE_SIZE)) : 1;

  const columns = React.useMemo<ColumnDef<AuditEntry, unknown>[]>(
    () => [
      {
        accessorKey: "occurred_at",
        header: "When",
        size: 180,
        meta: { mono: true, filter: false },
        cell: ({ getValue }) => format(new Date(getValue() as string), "dd MMM yyyy HH:mm:ss"),
      },
      { id: "actor", header: "User", size: 170, accessorFn: (e) => e.actor_name ?? (e.actor_id ? e.actor_id : "System") },
      {
        accessorKey: "action",
        header: "Action",
        size: 150,
        cell: ({ getValue }) => {
          const a = getValue() as string;
          return <StatusPill tone={ACTION_TONE[a] ?? "grey"}>{ACTION_LABEL[a] ?? a}</StatusPill>;
        },
      },
      { accessorKey: "entity_type", header: "Record type", size: 160, meta: { mono: true } },
      { accessorKey: "entity_id", header: "Record id", size: 300, meta: { mono: true } },
      {
        id: "changed",
        header: "Changed fields",
        size: 260,
        accessorFn: (e) => (e.changed_fields ?? []).join(", "),
        cell: ({ row }) => (
          <span className="flex gap-1 overflow-hidden">
            {(row.original.changed_fields ?? []).map((f) => (
              <Badge key={f} tone="outline" className="font-mono">
                {f}
              </Badge>
            ))}
          </span>
        ),
      },
      {
        id: "view",
        header: "",
        size: 90,
        enableSorting: false,
        meta: { filter: false, label: "Details" },
        cell: ({ row }) => (
          <Button size="sm" variant="ghost" onClick={() => setSelected(row.original)} aria-label={`View change ${row.original.id}`}>
            View
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <>
      <div className="mb-4 grid gap-3 rounded-lg border bg-white p-4 shadow-xs sm:grid-cols-2 lg:grid-cols-5" role="search" aria-label="Audit filters">
        <Field label="User" htmlFor="audit-user">
          <Select
            value={filters.actor_id ?? ALL}
            onValueChange={(v) => set({ actor_id: v === ALL ? undefined : v })}
            options={[{ value: ALL, label: "Anyone" }, ...(users.data?.items ?? []).map((u) => ({ value: u.id, label: `${u.full_name} (${u.username})` }))]}
          />
        </Field>
        <Field label="Record type" htmlFor="audit-type">
          <Select
            value={filters.entity_type ?? ALL}
            onValueChange={(v) => set({ entity_type: v === ALL ? undefined : v })}
            options={[{ value: ALL, label: "All types" }, ...(types.data ?? []).map((t) => ({ value: t, label: t }))]}
          />
        </Field>
        <Field label="Action" htmlFor="audit-action">
          <Select
            value={filters.action ?? ALL}
            onValueChange={(v) => set({ action: v === ALL ? undefined : v })}
            options={[{ value: ALL, label: "All actions" }, ...Object.entries(ACTION_LABEL).map(([value, label]) => ({ value, label }))]}
          />
        </Field>
        <Field label="From" htmlFor="audit-from">
          <DatePicker value={from} onChange={(d) => { setFrom(d); set({ date_from: d ? format(d, "yyyy-MM-dd") : undefined }); }} />
        </Field>
        <Field label="To" htmlFor="audit-to">
          <DatePicker value={to} onChange={(d) => { setTo(d); set({ date_to: d ? format(d, "yyyy-MM-dd") : undefined }); }} />
        </Field>
      </div>

      <DataTable
        id="audit"
        data={audit.data?.items ?? []}
        columns={columns}
        getRowId={(e) => String(e.id)}
        loading={audit.isPending}
        error={audit.isError ? audit.error.message : null}
        exportFileName="fabtrack-audit"
        emptyState={<EmptyState icon={History} title="No matching audit entries" description="Change the filters or widen the date range." />}
        toolbar={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setFrom(null);
              setTo(null);
              setFilters({ page: 1, page_size: PAGE_SIZE });
            }}
          >
            <RotateCcw /> Clear filters
          </Button>
        }
      />
      <div className="mt-3 flex items-center justify-end gap-2 text-sm text-neutral-600" aria-live="polite">
        <span className="tabular-nums">
          {audit.data ? `${audit.data.total.toLocaleString("en-IN")} entries · page ${filters.page} of ${pages}` : ""}
        </span>
        <Button variant="secondary" size="icon-sm" aria-label="Previous page" disabled={filters.page <= 1} onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}>
          <ChevronLeft />
        </Button>
        <Button variant="secondary" size="icon-sm" aria-label="Next page" disabled={filters.page >= pages} onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}>
          <ChevronRight />
        </Button>
      </div>

      <Drawer open={selected !== null} onOpenChange={(o) => !o && setSelected(null)}>
        <DrawerContent width="640px" title={selected ? `${ACTION_LABEL[selected.action] ?? selected.action}: ${selected.entity_type}` : ""}>
          {selected && (
            <div className="space-y-4">
              <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1.5 text-sm">
                <dt className="text-neutral-500">When</dt>
                <dd><MonoText>{format(new Date(selected.occurred_at), "dd MMM yyyy HH:mm:ss")}</MonoText></dd>
                <dt className="text-neutral-500">User</dt>
                <dd>{selected.actor_name ? `${selected.actor_name} (${selected.actor_username})` : "System"}</dd>
                <dt className="text-neutral-500">Record</dt>
                <dd><MonoText className="break-all">{selected.entity_id}</MonoText></dd>
                {selected.request_id && (
                  <>
                    <dt className="text-neutral-500">Request id</dt>
                    <dd><MonoText>{selected.request_id}</MonoText></dd>
                  </>
                )}
              </dl>
              <AuditDiff entry={selected} />
            </div>
          )}
        </DrawerContent>
      </Drawer>
    </>
  );
}

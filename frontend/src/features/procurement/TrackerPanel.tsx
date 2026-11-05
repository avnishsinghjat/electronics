import type { ColumnDef } from "@tanstack/react-table";
import { AlertTriangle, CheckCircle2, ClipboardList, PackageCheck } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  Button,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  DataTable,
  EmptyState,
  Field,
  Label,
  MonoText,
  Select,
  Skeleton,
  StatCard,
  StatusPill,
  Tooltip,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { LINE_STATUS_TONE } from "@/features/boq/api";
import { ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { type Tracker, type TrackerLine, money, qty, useProcurementMutations, useTracker } from "./api";

const ALL = "__all";
const STATUSES = ["Not ordered", "Partially ordered", "Ordered", "Partially received", "Received", "Issued", "Not required"];

const num = (accessor: keyof TrackerLine, header: string, size = 92): ColumnDef<TrackerLine, unknown> => ({
  id: accessor,
  accessorFn: (l) => Number(l[accessor] as string),
  header,
  size,
  meta: { mono: true, align: "right", exportType: "number" },
  cell: ({ getValue }) => {
    const v = getValue() as number;
    return <span className={cn(v === 0 && "text-neutral-400")}>{qty(v)}</span>;
  },
});

const columns: ColumnDef<TrackerLine, unknown>[] = [
  { accessorKey: "module_code", header: "Module", size: 100, meta: { mono: true }, cell: ({ getValue }) => (getValue() as string | null) ?? "Project" },
  { accessorKey: "ref_des", header: "Ref des", size: 130, meta: { mono: true } },
  { accessorKey: "mpn", header: "MPN", size: 180, meta: { mono: true } },
  { accessorKey: "description", header: "Description", size: 200 },
  { accessorKey: "category", header: "Category", size: 100 },
  num("required_qty", "Required"),
  num("ordered_qty", "Ordered"),
  num("received_qty", "Received"),
  num("issued_qty", "Issued", 80),
  num("shortfall", "To order"),
  num("pending_receipt", "Awaiting"),
  num("being_ordered", "On PR / draft PO", 110),
  {
    id: "expected",
    accessorFn: (l) => l.expected_date ?? "",
    header: "Expected",
    size: 110,
    meta: { mono: true, exportValue: (l: TrackerLine) => l.expected_date ?? "" },
    cell: ({ row }) => fmtDate(row.original.expected_date),
  },
  {
    accessorKey: "days_overdue",
    header: "Days late",
    size: 84,
    meta: { mono: true, align: "right", exportType: "number" },
    cell: ({ getValue }) => {
      const d = getValue() as number;
      return d > 0 ? <span className="font-semibold text-status-red-fg">{d}</span> : <span className="text-neutral-400">—</span>;
    },
  },
  { id: "vendors", accessorFn: (l) => l.vendors.join(", "), header: "Vendor", size: 170 },
  {
    id: "pos",
    accessorFn: (l) => l.purchase_orders.map((p) => p.po_number).join(", "),
    header: "Purchase orders",
    size: 170,
    meta: { mono: true },
    cell: ({ row }) => (
      <span className="flex flex-wrap gap-x-2">
        {row.original.purchase_orders.map((p) => (
          <Link key={p.po_id} to={`/procurement/orders/${p.po_id}`} className="font-mono text-accent-700 hover:underline">
            {p.po_number}
          </Link>
        ))}
      </span>
    ),
  },
  num("value_pending", "Value pending", 110),
  {
    accessorKey: "status",
    header: "Status",
    size: 150,
    cell: ({ row }) => <StatusPill tone={LINE_STATUS_TONE[row.original.status] ?? "grey"}>{row.original.dnp ? "DNP" : row.original.status}</StatusPill>,
  },
];

function Readiness({ tracker }: { tracker: Tracker }) {
  if (!tracker.modules.length) return null;
  return (
    <Card>
      <CardHeader title="Clear to build" description="Green only when every required line of the module's BOQ is received in full. DNP and zero-quantity lines do not count." />
      <CardContent>
        <ul className="flex flex-wrap gap-3" aria-label="Clear to build by module">
          {tracker.modules.map((m) => (
            <li key={m.module_id ?? "project"}>
              <Tooltip content={m.reason ?? "Every line received"}>
                <span
                  tabIndex={0}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm",
                    m.clear_to_build ? "border-status-green-border bg-status-green-bg text-status-green-fg" : "border-status-amber-border bg-status-amber-bg text-status-amber-fg",
                  )}
                >
                  {m.clear_to_build ? <CheckCircle2 className="size-4" aria-hidden="true" /> : <AlertTriangle className="size-4" aria-hidden="true" />}
                  <span className="font-medium">{m.module_code ?? m.module_name}</span>
                  <MonoText className="text-xs">
                    {m.lines_received}/{m.lines}
                  </MonoText>
                  <span className="sr-only">{m.clear_to_build ? "clear to build" : `not clear: ${m.reason}`}</span>
                </span>
              </Tooltip>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function TrackerPanel({ projectId }: { projectId: string }) {
  const tracker = useTracker(projectId);
  const canRaise = useCan("pr:create");
  const navigate = useNavigate();
  const { raisePr } = useProcurementMutations();
  const [status, setStatus] = React.useState(ALL);
  const [vendor, setVendor] = React.useState(ALL);
  const [module, setModule] = React.useState(ALL);
  const [overdueOnly, setOverdueOnly] = React.useState(false);
  const [groupBy, setGroupBy] = React.useState<"none" | "vendor" | "category">("none");
  const [selected, setSelected] = React.useState<TrackerLine[]>([]);

  if (tracker.isPending) return <Skeleton className="h-96" />;
  if (tracker.isError) return <p role="alert" className="text-sm text-status-red-fg">{tracker.error.message}</p>;
  const t = tracker.data;
  if (!t.lines.length) {
    return (
      <Card>
        <EmptyState icon={ClipboardList} title="Nothing to track yet" description="The tracker lists every line of the project's BOQs. Add or import a BOQ first." />
      </Card>
    );
  }

  const vendors = [...new Set(t.lines.flatMap((l) => l.vendors))].sort();
  const modules = [...new Map(t.lines.map((l) => [l.module_code ?? "Project", l.module_code ?? "Project"])).values()];
  const lines = t.lines.filter(
    (l) =>
      (status === ALL || (l.dnp ? "Not required" : l.status) === status) &&
      (vendor === ALL || l.vendors.includes(vendor)) &&
      (module === ALL || (l.module_code ?? "Project") === module) &&
      (!overdueOnly || l.days_overdue > 0),
  );
  const groups: [string, TrackerLine[]][] =
    groupBy === "none"
      ? [["", lines]]
      : [...lines.reduce((map, l) => {
          const keys = groupBy === "vendor" ? (l.vendors.length ? l.vendors : ["No vendor yet"]) : [l.category ?? "Uncategorised"];
          for (const k of keys) map.set(k, [...(map.get(k) ?? []), l]);
          return map;
        }, new Map<string, TrackerLine[]>())].sort(([a], [b]) => a.localeCompare(b));

  const shortSelected = selected.filter((l) => Number(l.shortfall) > Number(l.being_ordered));
  const raise = (ids: string[]) =>
    raisePr.mutate(
      { projectId, boq_line_ids: ids },
      {
        onSuccess: (pr) => {
          toast.success(`Requisition ${pr.number} raised with ${pr.lines.length} line${pr.lines.length === 1 ? "" : "s"}`);
          navigate(`/procurement/requisitions/${pr.id}`);
        },
        onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not raise the requisition"),
      },
    );

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="Tracker summary">
        <StatCard label="Lines fully received" value={`${t.kpis.pct_fully_received}%`} hint={`of ${t.kpis.lines_required} required lines`} />
        <StatCard label="Lines to order" value={t.kpis.lines_to_order} />
        <StatCard label="Awaiting delivery" value={t.kpis.lines_awaiting_delivery} />
        <StatCard label="Overdue lines" value={t.kpis.overdue_lines} />
        <StatCard label="Value pending" value={`₹ ${money(t.kpis.value_pending)}`} hint="ordered, not yet received" />
      </div>
      {t.unreleased_boqs.length > 0 && (
        <p role="status" className="flex items-start gap-2 rounded-md border border-status-amber-border bg-status-amber-bg px-3 py-2 text-sm text-status-amber-fg">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Not released yet, so not requisitioned: {t.unreleased_boqs.join(", ")}. Release the revision on the BOQ tab.
        </p>
      )}
      <Readiness tracker={t} />

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status" htmlFor="trk-status">
          <Select className="w-44" value={status} onValueChange={setStatus} options={[{ value: ALL, label: "All statuses" }, ...STATUSES.map((s) => ({ value: s, label: s }))]} />
        </Field>
        <Field label="Vendor" htmlFor="trk-vendor">
          <Select className="w-52" value={vendor} onValueChange={setVendor} options={[{ value: ALL, label: "All vendors" }, ...vendors.map((v) => ({ value: v, label: v }))]} />
        </Field>
        <Field label="Module" htmlFor="trk-module">
          <Select className="w-36" value={module} onValueChange={setModule} options={[{ value: ALL, label: "All modules" }, ...modules.map((m) => ({ value: m, label: m }))]} />
        </Field>
        <Field label="Group by" htmlFor="trk-group">
          <Select
            className="w-36"
            value={groupBy}
            onValueChange={(v) => setGroupBy(v as typeof groupBy)}
            options={[
              { value: "none", label: "No grouping" },
              { value: "vendor", label: "Vendor" },
              { value: "category", label: "Category" },
            ]}
          />
        </Field>
        <div className="flex items-center gap-2 pb-2">
          <Checkbox id="trk-overdue" checked={overdueOnly} onCheckedChange={(v) => setOverdueOnly(v === true)} />
          <Label htmlFor="trk-overdue">Overdue only</Label>
        </div>
        {canRaise && (
          <div className="ml-auto flex gap-2 pb-0.5">
            <Button
              variant="secondary"
              disabled={!shortSelected.length}
              loading={raisePr.isPending}
              onClick={() => raise(shortSelected.map((l) => l.boq_line_id))}
            >
              Requisition selected ({shortSelected.length})
            </Button>
            <Button disabled={t.kpis.lines_to_order === 0} loading={raisePr.isPending} onClick={() => raise([])}>
              <PackageCheck /> Requisition all shortfall
            </Button>
          </div>
        )}
      </div>

      {groups.map(([name, rows]) => (
        <section key={name || "all"} aria-label={name ? `Group ${name}` : "Tracker lines"} className="space-y-2">
          {name && (
            <h3 className="text-sm font-semibold text-neutral-800">
              {name} <span className="font-normal text-neutral-500">· {rows.length} lines</span>
            </h3>
          )}
          <DataTable
            id={`tracker-${groupBy}`}
            data={rows}
            columns={columns}
            getRowId={(l) => `${name}:${l.boq_line_id}`}
            enableSelection={canRaise}
            onSelectionChange={setSelected}
            exportFileName={`${t.project_code}-tracker${name ? `-${name}` : ""}`}
            maxHeight={groupBy === "none" ? 620 : 360}
            initialPinning={{ left: ["mpn"] }}
            emptyState={<p className="px-3 py-6 text-center text-sm text-neutral-500">No lines match these filters.</p>}
          />
        </section>
      ))}
    </div>
  );
}

import type { ColumnDef } from "@tanstack/react-table";
import { ArrowDown, ArrowUp, Copy, Factory, Plus, ShieldCheck, Tablet, Trash2 } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  DataTable,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  Input,
  MonoText,
  PageHeader,
  Select,
  StatusPill,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ConfirmDialog } from "@/features/procurement/PurchaseOrderPage";
import { ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { WoDrawer } from "./WoDrawer";
import {
  STAGE_CODES,
  type StageTemplate,
  type TemplateStep,
  WO_STATUS,
  type WoStatus,
  type WorkOrder,
  useBoard,
  useProductionMutations,
  useTemplates,
  useWorkOrders,
} from "./api";

const ALL = "__all";
const TABS = ["board", "orders", "templates"] as const;
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

/* ---------------------------------------------------------------- board */

function BoardTab() {
  const board = useBoard();
  if (board.isError) return <p role="alert" className="text-sm text-status-red-fg">{board.error.message}</p>;
  const columns = (board.data ?? []).filter((c) => c.cards.length > 0 || ["draft", "released", "completed"].includes(c.key));
  if (board.data && board.data.every((c) => c.cards.length === 0))
    return <Card><EmptyState icon={Factory} title="No work orders yet" description="Create a work order for a PCB assembly; it appears here and moves across as stages complete." /></Card>;
  return (
    <div className="flex gap-3 overflow-x-auto pb-3" aria-label="Work order board">
      {columns.map((col) => (
        <section key={col.key} aria-label={`Column ${col.label}`} className="flex w-64 shrink-0 flex-col rounded-lg border bg-neutral-50/70">
          <h2 className="flex items-center justify-between border-b px-3 py-2 text-sm font-semibold text-neutral-800">
            {col.label}
            <MonoText className="rounded bg-white px-1.5 text-xs text-neutral-500">{col.cards.length}</MonoText>
          </h2>
          <ul className="flex-1 space-y-2 p-2">
            {col.cards.map((c) => (
              <li key={c.work_order_id}>
                <Link to={`/production/work-orders/${c.work_order_id}`} className="block rounded-md border bg-white p-3 shadow-xs hover:border-accent-600 focus-visible:shadow-focus focus-visible:outline-none">
                  <div className="flex items-center justify-between">
                    <MonoText className="text-sm font-semibold text-accent-700">{c.number}</MonoText>
                    <MonoText className="text-xs text-neutral-500">{c.project_code}</MonoText>
                  </div>
                  <p className="mt-1 truncate text-xs text-neutral-600">{c.assembly_label} · {c.build_qty} boards</p>
                  {c.stage_name && c.status === "in_progress" && (
                    <p className="mt-2 text-xs text-neutral-700">
                      Stage {c.stage_seq}/{c.stage_count}: <MonoText>{c.units_done_at_stage}/{c.units_at_stage}</MonoText> done
                      {c.awaiting_qc > 0 && <span className="ml-1 text-status-amber-fg">· {c.awaiting_qc} awaiting QC</span>}
                    </p>
                  )}
                  {c.planned_end && <p className="mt-1 text-xs text-neutral-500">Due {fmtDate(c.planned_end)}</p>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- work order list */

export const woColumns: ColumnDef<WorkOrder, unknown>[] = [
  { accessorKey: "number", header: "Work order", size: 130, meta: { mono: true }, cell: ({ row }) => <Link to={`/production/work-orders/${row.original.id}`} className="font-mono text-accent-700 hover:underline">{row.original.number}</Link> },
  { accessorKey: "project_code", header: "Project", size: 140, meta: { mono: true } },
  { accessorKey: "assembly_label", header: "Assembly", size: 240 },
  { accessorKey: "lot_number", header: "Lot", size: 130, meta: { mono: true } },
  { accessorKey: "build_qty", header: "Qty", size: 64, meta: { mono: true, align: "right", exportType: "number" } },
  { accessorKey: "units_completed", header: "Done", size: 64, meta: { mono: true, align: "right", exportType: "number" } },
  { accessorKey: "current_stage", header: "Current stage", size: 150 },
  { accessorKey: "planned_end", header: "Due", size: 110, meta: { mono: true }, cell: ({ row }) => fmtDate(row.original.planned_end) },
  { accessorKey: "status", header: "Status", size: 130, meta: { exportValue: (w: WorkOrder) => WO_STATUS[w.status].label }, cell: ({ row }) => <StatusPill tone={WO_STATUS[row.original.status].tone}>{WO_STATUS[row.original.status].label}</StatusPill> },
];

function OrdersTab() {
  const [status, setStatus] = React.useState(ALL);
  const orders = useWorkOrders(status === ALL ? {} : { status });
  return (
    <div className="space-y-4">
      <Field label="Status" htmlFor="wo-status" className="w-52">
        <Select value={status} onValueChange={setStatus} options={[{ value: ALL, label: "All" }, ...(Object.keys(WO_STATUS) as WoStatus[]).map((s) => ({ value: s, label: WO_STATUS[s].label }))]} />
      </Field>
      <DataTable id="work-orders" data={orders.data ?? []} columns={woColumns} getRowId={(w) => w.id} loading={orders.isPending} exportFileName="work-orders" />
    </div>
  );
}

/* ---------------------------------------------------------------- stage templates */

function TemplateEditor({ template, onClose }: { template: StageTemplate; onClose: () => void }) {
  const { updateTemplate } = useProductionMutations();
  const [name, setName] = React.useState(template.name);
  const [steps, setSteps] = React.useState<TemplateStep[]>(template.steps.map(({ stage_code, name: n, requires_qc }) => ({ stage_code, name: n, requires_qc })));
  const set = (i: number, patch: Partial<TemplateStep>) => setSteps((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const move = (i: number, d: -1 | 1) =>
    setSteps((s) => {
      const next = s.slice();
      const [item] = next.splice(i, 1);
      if (item) next.splice(i + d, 0, item);
      return next;
    });
  const save = () => {
    if (steps.some((s) => !s.name.trim())) return toast.error("Every stage needs a name");
    updateTemplate.mutate(
      { id: template.id, row_version: template.row_version, name: name.trim(), description: template.description, steps },
      { onSuccess: () => { toast.success("Stage template saved"); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
    );
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="lg"
        title={`Edit ${template.name}`}
        description="Order the stages, add custom ones and mark which need a passed QC inspection before the next stage. New work orders copy these stages."
        footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={updateTemplate.isPending}>Save template</Button></>}
      >
        <div className="space-y-4">
          <Field label="Template name" htmlFor="tpl-name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <ol className="space-y-2" aria-label="Stages">
            {steps.map((s, i) => (
              <li key={i} className="grid grid-cols-[1.5rem_10rem_minmax(0,1fr)_auto_auto] items-center gap-2" aria-label={`Stage ${i + 1}`}>
                <MonoText className="text-right text-xs text-neutral-500">{i + 1}</MonoText>
                <Select aria-label={`Stage ${i + 1} type`} className="h-8" value={s.stage_code} onValueChange={(v) => set(i, { stage_code: v })} options={STAGE_CODES} />
                <Input aria-label={`Stage ${i + 1} name`} className="h-8" value={s.name} onChange={(e) => set(i, { name: e.target.value })} />
                <label className="flex items-center gap-1.5 text-xs text-neutral-700">
                  <Checkbox aria-label={`Stage ${i + 1} requires QC`} checked={s.requires_qc} onCheckedChange={(v) => set(i, { requires_qc: v === true })} /> QC
                </label>
                <span className="flex">
                  <Button size="icon-sm" variant="ghost" aria-label={`Move stage ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
                  <Button size="icon-sm" variant="ghost" aria-label={`Move stage ${i + 1} down`} disabled={i === steps.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
                  <Button size="icon-sm" variant="ghost" aria-label={`Remove stage ${i + 1}`} disabled={steps.length === 1} onClick={() => setSteps((x) => x.filter((_, j) => j !== i))}><Trash2 /></Button>
                </span>
              </li>
            ))}
          </ol>
          <Button variant="secondary" size="sm" onClick={() => setSteps((s) => [...s, { stage_code: "custom", name: "", requires_qc: false }])}><Plus /> Add stage</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TemplatesTab() {
  const templates = useTemplates();
  const canManage = useCan("wo:manage");
  const { createTemplate, deleteTemplate } = useProductionMutations();
  const [editing, setEditing] = React.useState<StageTemplate | null>(null);
  const [deleting, setDeleting] = React.useState<StageTemplate | null>(null);
  const copy = (t: StageTemplate) =>
    createTemplate.mutate(
      { name: `${t.name} (copy ${new Date().toISOString().slice(11, 19)})`, description: t.description, copy_from_id: t.id },
      { onSuccess: (n) => { toast.success(`${n.name} created`); setEditing(n); }, onError: (e) => toast.error(errMsg(e)) },
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-neutral-600">Each PCB assembly uses one template (set it in the assembly's details on the project page); the default applies otherwise.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {(templates.data ?? []).map((t) => (
          <Card key={t.id}>
            <CardHeader
              title={t.name}
              description={`${t.steps.length} stages · used by ${t.assembly_count} assembl${t.assembly_count === 1 ? "y" : "ies"}`}
              actions={
                canManage && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => copy(t)} aria-label={`Copy ${t.name}`}><Copy /></Button>
                    {!t.is_default && <Button size="sm" variant="secondary" onClick={() => setEditing(t)}>Edit</Button>}
                    {!t.is_default && <Button size="sm" variant="ghost" aria-label={`Delete ${t.name}`} onClick={() => setDeleting(t)}><Trash2 /></Button>}
                  </span>
                )
              }
            />
            <CardContent>
              {t.is_default && <Badge tone="outline" className="mb-2">Default (copy it to change)</Badge>}
              <ol className="flex flex-wrap gap-1.5 text-xs">
                {t.steps.map((s) => (
                  <li key={s.id ?? s.name} className={cn("inline-flex items-center gap-1 rounded border px-2 py-1", s.requires_qc && "border-status-amber-border bg-status-amber-bg")}>
                    <MonoText className="text-neutral-600">{s.seq}</MonoText> {s.name}
                    {s.requires_qc && <ShieldCheck className="size-3 text-status-amber-fg" aria-label="requires QC" />}
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        ))}
      </div>
      {editing && <TemplateEditor template={editing} onClose={() => setEditing(null)} />}
      <ConfirmDialog
        open={!!deleting}
        title={`Delete ${deleting?.name ?? ""}?`}
        description="Only templates no assembly uses can be deleted. Existing work orders keep their stages."
        confirmLabel="Delete template"
        destructive
        busy={deleteTemplate.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && deleteTemplate.mutate({ id: deleting.id, row_version: deleting.row_version }, { onSuccess: () => { toast.success("Template deleted"); setDeleting(null); }, onError: (e) => toast.error(errMsg(e)) })}
      />
    </div>
  );
}

export default function ProductionPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") ?? "board";
  const tab = (TABS as readonly string[]).includes(raw) ? raw : "board";
  const canManage = useCan("wo:manage");
  const [creating, setCreating] = React.useState(false);
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Production" }]}
        title="Production"
        description="Work orders by stage, kitting, serial numbers and shop-floor progress."
        secondaryActions={<Button asChild variant="secondary"><Link to="/shop-floor"><Tablet /> Shop-floor mode</Link></Button>}
        primaryAction={canManage && <Button onClick={() => setCreating(true)}><Plus /> New work order</Button>}
      />
      <Tabs value={tab} onValueChange={(v) => setParams(v === "board" ? {} : { tab: v }, { replace: true })}>
        <TabsList aria-label="Production sections">
          <TabsTrigger value="board">Board</TabsTrigger>
          <TabsTrigger value="orders">Work orders</TabsTrigger>
          <TabsTrigger value="templates">Stage templates</TabsTrigger>
        </TabsList>
        <TabsContent value="board"><BoardTab /></TabsContent>
        <TabsContent value="orders"><OrdersTab /></TabsContent>
        <TabsContent value="templates"><TemplatesTab /></TabsContent>
      </Tabs>
      <WoDrawer open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

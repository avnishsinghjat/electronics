import type { ColumnDef } from "@tanstack/react-table";
import { AlertTriangle, CheckCircle2, FileText, GitBranch, PackageMinus, PackagePlus, Pencil, QrCode, Send, Tablet, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  Input,
  MonoText,
  NumberInput,
  PageHeader,
  Select,
  Skeleton,
  StatCard,
  StatusPill,
  type Step,
  Stepper,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { useLocations } from "@/features/inventory/api";
import { ConfirmDialog } from "@/features/procurement/PurchaseOrderPage";
import { ApiError, apiBlob } from "@/lib/api";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { LotStageActions, UnitStageActions } from "./StageActions";
import { WoDrawer } from "./WoDrawer";
import {
  type Genealogy,
  type KitLine,
  type KitRecord,
  STAGE_STATUS,
  type StageSummary,
  UNIT_STATUS,
  type Unit,
  WO_STATUS,
  type WorkOrderDetail,
  fetchGenealogy,
  useKit,
  useKitRecords,
  useLots,
  useProductionMutations,
  useUnits,
  useWorkOrder,
} from "./api";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");
const q = (v: string | number | null | undefined) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 4 }));

function stepState(s: StageSummary): Step["state"] {
  if (s.status === "completed") return "complete";
  if (s.status === "in_progress" || s.status === "awaiting_qc") return "current";
  return "upcoming";
}

/* ---------------------------------------------------------------- release */

function ReleaseDialog({ wo, onClose }: { wo: WorkOrderDetail; onClose: () => void }) {
  const canOverride = useCan("wo:override_release");
  const { release } = useProductionMutations();
  const [reason, setReason] = React.useState("");
  const ready = wo.readiness;
  const clear = !!ready?.clear_to_build;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="md"
        title={`Release ${wo.number}`}
        description={`${wo.build_qty} × ${wo.assembly_label}`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              disabled={!clear && (!canOverride || reason.trim().length < 5)}
              loading={release.isPending}
              onClick={() =>
                release.mutate(
                  { id: wo.id, row_version: wo.row_version, override_reason: clear ? null : reason.trim() },
                  { onSuccess: () => { toast.success(`${wo.number} released to production`); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
                )
              }
            >
              <Send /> {clear ? "Release" : "Release with override"}
            </Button>
          </>
        }
      >
        {clear ? (
          <p className="flex items-center gap-2 text-sm text-status-green-fg"><CheckCircle2 className="size-4" aria-hidden="true" /> Clear to build: every BOQ line of {wo.module_code ?? "the module"} is received.</p>
        ) : (
          <div className="space-y-4">
            <p role="alert" className="flex items-start gap-2 rounded-md border border-status-amber-border bg-status-amber-bg px-3 py-2 text-sm text-status-amber-fg">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> Not clear to build: {ready?.reason ?? "no BOQ"}.
            </p>
            {canOverride ? (
              <Field label="Reason for releasing anyway" htmlFor="rel-reason" required hint="Recorded in the audit log with your name">
                <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Client approved a pilot lot; missing connectors are fitted at final assembly" />
              </Field>
            ) : (
              <p className="text-sm text-neutral-600">Only a project manager can release it before every part is received.</p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- kitting */

function IssueDialog({ wo, line, onClose }: { wo: WorkOrderDetail; line: KitLine; onClose: () => void }) {
  const lots = useLots(line.part_id);
  const { issue } = useProductionMutations();
  const [picks, setPicks] = React.useState<Record<string, string>>({});
  const key = (l: { location_id: string; lot_code: string | null }) => `${l.location_id}|${l.lot_code ?? ""}`;
  // Suggest oldest lots first up to the shortage.
  const suggested = React.useMemo(() => {
    let left = Number(line.shortage);
    const out: Record<string, string> = {};
    for (const l of lots.data ?? []) {
      if (left <= 0) break;
      const take = Math.min(left, Number(l.qty));
      out[key(l)] = String(take);
      left -= take;
    }
    return out;
  }, [lots.data, line.shortage]);
  const value = (k: string) => picks[k] ?? suggested[k] ?? "";
  const total = (lots.data ?? []).reduce((s, l) => s + (Number(value(key(l))) || 0), 0);
  const submit = () => {
    const issues = (lots.data ?? [])
      .filter((l) => Number(value(key(l))) > 0)
      .map((l) => ({ boq_line_id: line.boq_line_id, location_id: l.location_id, qty: String(Number(value(key(l)))), lot_code: l.lot_code, note: null }));
    if (!issues.length) return toast.error("Enter a quantity for at least one lot");
    issue.mutate(
      { id: wo.id, issues },
      { onSuccess: () => { toast.success(`${q(total)} × ${line.mpn} issued to ${wo.number}`); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
    );
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="md"
        title={`Issue ${line.mpn}`}
        description={`Needed ${q(line.required)}, issued ${q(line.issued)}, still short ${q(line.shortage)}. Oldest lots are suggested first.`}
        footer={<><span className="mr-auto text-sm text-neutral-600">Issuing <MonoText className="font-semibold">{q(total)}</MonoText></span><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={issue.isPending}><PackageMinus /> Issue</Button></>}
      >
        {lots.isPending ? (
          <Skeleton className="h-24" />
        ) : !lots.data?.length ? (
          <p className="text-sm text-status-red-fg">No usable stock of this part.</p>
        ) : (
          <table className="w-full text-sm" aria-label="Lots in stock">
            <thead className="text-left text-xs font-semibold text-neutral-600">
              <tr><th className="py-1">Location</th><th className="py-1">Lot</th><th className="py-1 text-right">In stock</th><th className="py-1 text-right">Issue</th></tr>
            </thead>
            <tbody>
              {lots.data.map((l) => (
                <tr key={key(l)} className="border-t">
                  <td className="py-1.5 font-mono text-xs">{l.location_code}</td>
                  <td className="py-1.5 font-mono text-xs">{l.lot_code ?? "—"}</td>
                  <td className="py-1.5 text-right font-mono">{q(l.qty)}</td>
                  <td className="py-1.5 text-right">
                    <Input aria-label={`Issue from ${l.location_code} lot ${l.lot_code ?? "none"}`} inputMode="decimal" className="ml-auto h-8 w-24 text-right font-mono" value={value(key(l))} onChange={(e) => setPicks((p) => ({ ...p, [key(l)]: e.target.value }))} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReturnDialog({ wo, line, records, onClose }: { wo: WorkOrderDetail; line: KitLine; records: KitRecord[]; onClose: () => void }) {
  const locations = useLocations();
  const { returnParts } = useProductionMutations();
  const lots = new Map<string, number>();
  for (const r of records.filter((x) => x.boq_line_id === line.boq_line_id)) {
    const k = r.lot_code ?? "";
    lots.set(k, (lots.get(k) ?? 0) + (r.kind === "issue" ? 1 : -1) * Number(r.qty));
  }
  const options = [...lots.entries()].filter(([, v]) => v > 0);
  const [lot, setLot] = React.useState(options[0]?.[0] ?? "");
  const [qty, setQty] = React.useState<number | null>(null);
  const [loc, setLoc] = React.useState("");
  const [note, setNote] = React.useState("");
  const location = loc || locations.data?.find((l) => l.code === "STORES")?.id || "";
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`Return ${line.mpn} to stores`}
        description="Unused parts go back into stock, reserved for the project again."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              loading={returnParts.isPending}
              disabled={!qty || !location}
              onClick={() =>
                returnParts.mutate(
                  { id: wo.id, boq_line_id: line.boq_line_id, location_id: location, qty: String(qty), lot_code: lot || null, note: note.trim() || null },
                  { onSuccess: () => { toast.success(`${qty} × ${line.mpn} returned`); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
                )
              }
            >
              <PackagePlus /> Return
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <Field label="Lot" htmlFor="ret-lot">
            <Select value={lot || "__none"} onValueChange={(v) => setLot(v === "__none" ? "" : v)} options={options.map(([k, v]) => ({ value: k || "__none", label: `${k || "(no lot)"} · ${q(v)} issued` }))} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Quantity" htmlFor="ret-qty"><NumberInput value={qty} onValueChange={setQty} min={0} precision={0} /></Field>
            <Field label="To location" htmlFor="ret-loc"><Select value={location || undefined} onValueChange={setLoc} options={(locations.data ?? []).map((l) => ({ value: l.id, label: l.code }))} /></Field>
          </div>
          <Field label="Note" htmlFor="ret-note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Spare after SMT" /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function KitPanel({ wo }: { wo: WorkOrderDetail }) {
  const kit = useKit(wo.id);
  const records = useKitRecords(wo.id);
  const canKit = useCan("kitting:issue");
  const active = wo.status === "released" || wo.status === "in_progress";
  const [issuing, setIssuing] = React.useState<KitLine | null>(null);
  const [returning, setReturning] = React.useState<KitLine | null>(null);
  if (kit.isPending) return <Skeleton className="h-64" />;
  if (kit.isError) return <p role="alert" className="text-sm text-status-red-fg">{kit.error.message}</p>;
  if (!kit.data.boq_id) return <Card><EmptyState title="No BOQ to kit from" description="This board has no BOQ in the project. Add one on the project's BOQ tab, then edit the work order." /></Card>;
  const lines = kit.data.lines.filter((l) => !l.dnp && Number(l.required) > 0);
  const shortages = lines.filter((l) => Number(l.shortage) > 0);
  const columns: ColumnDef<KitLine, unknown>[] = [
    { accessorKey: "line_no", header: "#", size: 50, meta: { mono: true, align: "right" } },
    { accessorKey: "ref_des", header: "Ref des", size: 140, meta: { mono: true } },
    { accessorKey: "mpn", header: "MPN", size: 180, meta: { mono: true } },
    { accessorKey: "description", header: "Description", size: 200 },
    { id: "req", accessorFn: (l) => Number(l.required), header: "Needed", size: 84, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q(getValue() as number) },
    { id: "iss", accessorFn: (l) => Number(l.issued), header: "Issued", size: 84, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q(getValue() as number) },
    { id: "short", accessorFn: (l) => Number(l.shortage), header: "Short", size: 84, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => <strong className={cn((getValue() as number) > 0 && "text-status-amber-fg")}>{q(getValue() as number)}</strong> },
    { id: "res", accessorFn: (l) => Number(l.reserved_for_project), header: "Reserved", size: 88, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q(getValue() as number) },
    { id: "avail", accessorFn: (l) => Number(l.available), header: "In stock", size: 84, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ row }) => <span className={cn(Number(row.original.available) < Number(row.original.shortage) && "text-status-red-fg")}>{q(row.original.available)}</span> },
    {
      id: "act",
      header: "",
      size: 160,
      enableSorting: false,
      cell: ({ row }) =>
        canKit && active ? (
          <span className="flex gap-1">
            {Number(row.original.shortage) > 0 &&
              (Number(row.original.available) > 0 ? (
                <Button size="sm" variant="secondary" onClick={() => setIssuing(row.original)}>Issue</Button>
              ) : (
                <span className="px-2 text-xs text-neutral-600">No stock</span>
              ))}
            {Number(row.original.issued) > 0 && <Button size="sm" variant="ghost" onClick={() => setReturning(row.original)}>Return</Button>}
          </span>
        ) : null,
    },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-neutral-600">Kitting from <strong>{kit.data.boq_name}</strong> rev <MonoText>{kit.data.revision}</MonoText> for {wo.build_qty} boards</span>
        {kit.data.complete ? <StatusPill tone="green">Fully kitted</StatusPill> : <StatusPill tone="amber">{shortages.length} line{shortages.length === 1 ? "" : "s"} short</StatusPill>}
        {!active && wo.status === "draft" && <Badge tone="outline">Release the order to start kitting</Badge>}
      </div>
      <DataTable id="kit-lines" data={lines} columns={columns} getRowId={(l) => l.boq_line_id} exportFileName={`${wo.number}-kit`} />
      <Card>
        <CardHeader title="Issues and returns" description="Every row is an inventory ledger entry against the BOQ line, with the part lot." />
        <CardContent>
          {records.data?.length ? (
            <ul className="divide-y text-sm">
              {records.data.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-3 py-1.5">
                  <StatusPill tone={r.kind === "issue" ? "blue" : "green"}>{r.kind === "issue" ? "Issued" : "Returned"}</StatusPill>
                  <MonoText>{r.mpn}</MonoText>
                  <MonoText className="font-semibold">{r.kind === "issue" ? "−" : "+"}{q(r.qty)}</MonoText>
                  <span className="text-neutral-500">lot <MonoText>{r.lot_code ?? "—"}</MonoText> · {r.location_code}</span>
                  <span className="ml-auto text-xs text-neutral-500">{r.created_by_name} · {fmtDateTime(r.created_at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-500">Nothing issued yet.</p>
          )}
        </CardContent>
      </Card>
      {issuing && <IssueDialog wo={wo} line={issuing} onClose={() => setIssuing(null)} />}
      {returning && <ReturnDialog wo={wo} line={returning} records={records.data ?? []} onClose={() => setReturning(null)} />}
    </div>
  );
}

/* ---------------------------------------------------------------- progress and serials */

function GenealogyDialog({ unit, onClose }: { unit: Unit; onClose: () => void }) {
  const [g, setG] = React.useState<Genealogy | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    fetchGenealogy(unit.id).then(setG, (e: unknown) => setError(errMsg(e)));
  }, [unit.id]);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="lg" title={`Genealogy of ${unit.serial_number}`} description="Part lots kitted to this unit's work order (kitting is per work order, so every unit of the lot shares them).">
        {error ? (
          <p role="alert" className="text-sm text-status-red-fg">{error}</p>
        ) : !g ? (
          <Skeleton className="h-32" />
        ) : g.parts.length === 0 ? (
          <p className="text-sm text-neutral-500">No parts have been kitted to {g.work_order_number} yet.</p>
        ) : (
          <table className="w-full text-sm" aria-label="Part lots">
            <thead className="text-left text-xs font-semibold text-neutral-600"><tr><th className="py-1">Ref des</th><th className="py-1">MPN</th><th className="py-1">Lot</th><th className="py-1 text-right">Qty</th></tr></thead>
            <tbody>
              {g.parts.map((p) => (
                <tr key={`${p.boq_line_id}-${p.lot_code}`} className="border-t">
                  <td className="py-1.5 font-mono text-xs">{p.ref_des ?? "—"}</td>
                  <td className="py-1.5 font-mono text-xs">{p.mpn}</td>
                  <td className="py-1.5 font-mono text-xs">{p.lot_code ?? "—"}</td>
                  <td className="py-1.5 text-right font-mono">{q(p.qty)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SerialProgress({ wo }: { wo: WorkOrderDetail }) {
  const units = useUnits(wo.id);
  const canPlan = useCan("wo:manage");
  const { serials } = useProductionMutations();
  const [genealogy, setGenealogy] = React.useState<Unit | null>(null);
  const active = wo.status === "released" || wo.status === "in_progress";
  const stageById = new Map(wo.stages.map((s) => [s.id, s]));
  const openLabels = async () => {
    try {
      const url = URL.createObjectURL(await apiBlob(`/work-orders/${wo.id}/labels.pdf`));
      window.open(url, "_blank", "noopener");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const remaining = wo.build_qty - (units.data?.length ?? 0);
  const columns: ColumnDef<Unit, unknown>[] = [
    { accessorKey: "serial_number", header: "Serial", size: 220, meta: { mono: true } },
    { accessorKey: "status", header: "Unit", size: 130, cell: ({ row }) => <StatusPill tone={UNIT_STATUS[row.original.status].tone}>{UNIT_STATUS[row.original.status].label}</StatusPill> },
    { accessorKey: "current_stage", header: "Stage", size: 170, cell: ({ row }) => row.original.current_stage ?? (row.original.status === "passed" ? "All stages done" : "—") },
    { id: "stage_status", accessorFn: (u) => u.current_stage_status ?? "", header: "Stage status", size: 140, cell: ({ row }) => (row.original.current_stage_status ? <StatusPill tone={STAGE_STATUS[row.original.current_stage_status].tone}>{STAGE_STATUS[row.original.current_stage_status].label}</StatusPill> : null) },
    {
      id: "act",
      header: "",
      size: 280,
      enableSorting: false,
      cell: ({ row }) => {
        const u = row.original;
        const stage = u.current_stage_id ? stageById.get(u.current_stage_id) : undefined;
        if (!active || !stage || u.status === "failed") return null;
        const action = u.current_stage_status === "not_started" ? "start" : u.current_stage_status === "in_progress" ? (stage.requires_qc ? "finish" : "complete") : u.current_stage_status === "awaiting_qc" ? "complete" : null;
        return <UnitStageActions stageId={stage.id} unitId={u.id} serial={u.serial_number} action={action} requiresQc={stage.requires_qc} />;
      },
    },
    {
      id: "gen",
      header: "",
      size: 60,
      enableSorting: false,
      cell: ({ row }) => (
        <Button size="icon-sm" variant="ghost" aria-label={`Genealogy of ${row.original.serial_number}`} onClick={() => setGenealogy(row.original)}>
          <GitBranch />
        </Button>
      ),
    },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {canPlan && remaining > 0 && wo.status !== "cancelled" && wo.status !== "closed" && (
          <Button
            variant="secondary"
            loading={serials.isPending}
            onClick={() => serials.mutate({ id: wo.id, count: null }, { onSuccess: (u) => toast.success(`${u.length} serial numbers ready`), onError: (e) => toast.error(errMsg(e)) })}
          >
            <QrCode /> Generate {remaining} serial number{remaining === 1 ? "" : "s"}
          </Button>
        )}
        {(units.data?.length ?? 0) > 0 && <Button variant="secondary" onClick={() => void openLabels()}><FileText /> Print labels (PDF)</Button>}
        <Button asChild variant="ghost"><Link to="/shop-floor"><Tablet /> Shop-floor mode</Link></Button>
      </div>
      <DataTable
        id="wo-units"
        data={units.data ?? []}
        columns={columns}
        getRowId={(u) => u.id}
        loading={units.isPending}
        exportFileName={`${wo.number}-units`}
        emptyState={<EmptyState icon={QrCode} title="No serial numbers yet" description="Generate them, print the labels and stick one on each board before SMT." />}
      />
      {genealogy && <GenealogyDialog unit={genealogy} onClose={() => setGenealogy(null)} />}
    </div>
  );
}

function LotProgress({ wo }: { wo: WorkOrderDetail }) {
  const active = wo.status === "released" || wo.status === "in_progress";
  const firstOpen = wo.stages.find((s) => s.status !== "completed");
  return (
    <Card>
      <CardHeader title={`Lot ${wo.lot_number ?? ""}`} description="Tracked by lot: each stage is started and completed for the whole lot, with the quantities passed and failed." />
      <CardContent>
        <ol className="divide-y">
          {wo.stages.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 py-3" aria-label={`Stage ${s.seq} ${s.name}`}>
              <MonoText className="w-6 text-right text-neutral-500">{s.seq}</MonoText>
              <span className="w-44 font-medium">{s.name}{s.requires_qc && <Badge tone="outline" className="ml-2">QC</Badge>}</span>
              <StatusPill tone={STAGE_STATUS[s.status].tone}>{STAGE_STATUS[s.status].label}</StatusPill>
              <span className="text-sm text-neutral-600"><MonoText>{s.units_done}</MonoText> passed · <MonoText>{s.units_failed}</MonoText> failed of <MonoText>{s.units_in}</MonoText></span>
              <span className="ml-auto">
                {active && firstOpen?.id === s.id && <LotStageActions stageId={s.id} status={s.status} unitsIn={s.units_in} requiresQc={s.requires_qc} stageName={s.name} />}
              </span>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------- page */

export default function WorkOrderPage() {
  const { woId = "" } = useParams();
  const wo = useWorkOrder(woId);
  const canManage = useCan("wo:manage");
  const canRelease = useCan("wo:release");
  const { woAction } = useProductionMutations();
  const [releasing, setReleasing] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [confirm, setConfirm] = React.useState<"cancel" | "close" | null>(null);
  const [tab, setTab] = React.useState("progress");

  if (wo.isPending) return <Skeleton className="h-96" />;
  if (wo.isError) return <Card><EmptyState title="Work order not available" description={wo.error.message} action={<Button asChild variant="secondary"><Link to="/production">Back to production</Link></Button>} /></Card>;
  const w = wo.data;
  const s = WO_STATUS[w.status];
  const steps: Step[] = w.stages.map((st) => ({
    id: st.id,
    label: st.name,
    state: stepState(st),
    detail: st.status === "awaiting_qc" ? "awaiting QC" : st.units_in ? `${st.units_done}/${st.units_in}` : undefined,
  }));

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Production", to: "/production" }, { label: w.number }]}
        title={`Work order ${w.number}`}
        meta={
          <>
            <StatusPill tone={s.tone}>{s.label}</StatusPill>
            <span className="text-sm text-neutral-700">{w.assembly_label}</span>
            <Badge tone="outline"><Link to={`/projects/${w.project_id}?tab=production`} className="font-mono text-accent-700 hover:underline">{w.project_code}</Link></Badge>
            {w.lot_number && <Badge tone="outline">Lot <MonoText className="ml-1">{w.lot_number}</MonoText></Badge>}
            {w.release_override_reason && <Badge tone="outline" title={w.release_override_reason}>Released by override</Badge>}
          </>
        }
        secondaryActions={
          <>
            {canManage && w.status === "draft" && <Button variant="secondary" onClick={() => setEditing(true)}><Pencil /> Edit</Button>}
            {canManage && (w.status === "draft" || w.status === "released") && <Button variant="ghost" onClick={() => setConfirm("cancel")}><XCircle /> Cancel</Button>}
            {canManage && w.status === "completed" && <Button variant="secondary" onClick={() => setConfirm("close")}>Close order</Button>}
          </>
        }
        primaryAction={w.status === "draft" && canRelease && <Button onClick={() => setReleasing(true)}><Send /> Release to production</Button>}
      />
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-4">
          <StatCard label="Build quantity" value={w.build_qty} hint={w.track_serials ? `${w.serial_count} serialised` : "tracked by lot"} />
          <StatCard label="Completed" value={w.units_completed} hint={w.units_failed ? `${w.units_failed} failed` : undefined} />
          <StatCard label="Current stage" value={w.current_stage ?? (w.status === "draft" ? "Not released" : "—")} />
          <StatCard label="Planned" value={fmtDate(w.planned_end)} hint={w.planned_start ? `from ${fmtDate(w.planned_start)}` : undefined} />
        </div>
        {w.status === "draft" && w.readiness && (
          <p role="status" className={cn("flex items-center gap-2 rounded-md border px-3 py-2 text-sm", w.readiness.clear_to_build ? "border-status-green-border bg-status-green-bg text-status-green-fg" : "border-status-amber-border bg-status-amber-bg text-status-amber-fg")}>
            {w.readiness.clear_to_build ? <CheckCircle2 className="size-4" aria-hidden="true" /> : <AlertTriangle className="size-4" aria-hidden="true" />}
            {w.readiness.clear_to_build ? "Clear to build: every part is in stores." : `Not clear to build: ${w.readiness.reason}.`}
          </p>
        )}
        <Card>
          <CardContent className="pt-5">
            <Stepper steps={steps} />
          </CardContent>
        </Card>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList aria-label="Work order sections">
            <TabsTrigger value="progress">{w.track_serials ? "Units and stages" : "Stages"}</TabsTrigger>
            <TabsTrigger value="kit">Kitting</TabsTrigger>
          </TabsList>
          <TabsContent value="progress">{w.track_serials ? <SerialProgress wo={w} /> : <LotProgress wo={w} />}</TabsContent>
          <TabsContent value="kit"><KitPanel wo={w} /></TabsContent>
        </Tabs>
        {w.release_override_reason && (
          <p className="text-sm text-neutral-600">Released before clear to build: <em>{w.release_override_reason}</em></p>
        )}
      </div>
      {releasing && <ReleaseDialog wo={w} onClose={() => setReleasing(false)} />}
      <WoDrawer open={editing} wo={w} onClose={() => setEditing(false)} />
      <ConfirmDialog
        open={confirm === "cancel"}
        title={`Cancel ${w.number}?`}
        description="The lot is scrapped and no more progress can be recorded. Kitted parts must be returned first."
        confirmLabel="Cancel work order"
        destructive
        busy={woAction.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => woAction.mutate({ id: w.id, action: "cancel", row_version: w.row_version }, { onSuccess: () => { toast.success(`${w.number} cancelled`); setConfirm(null); }, onError: (e) => toast.error(errMsg(e)) })}
      />
      <ConfirmDialog
        open={confirm === "close"}
        title={`Close ${w.number}?`}
        description="The order is finished; it leaves the production board."
        confirmLabel="Close order"
        busy={woAction.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => woAction.mutate({ id: w.id, action: "close", row_version: w.row_version }, { onSuccess: () => { toast.success(`${w.number} closed`); setConfirm(null); }, onError: (e) => toast.error(errMsg(e)) })}
      />
    </>
  );
}

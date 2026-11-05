import type { ColumnDef } from "@tanstack/react-table";
import { GitCompareArrows, ListChecks, Plus, Save, Send, Trash2, Upload } from "lucide-react";
import * as React from "react";

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
  Select,
  Skeleton,
  StatusPill,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import type { ProjectTree } from "@/features/projects/api";
import { ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { BoqGrid, type GridRow, rowsFromLines, rowsToInput } from "./BoqGrid";
import { ImportWizard } from "./ImportWizard";
import {
  type Boq,
  type BoqLine,
  CATEGORIES,
  type DiffLine,
  LINE_STATUS_TONE,
  REVISION_TONE,
  type RevisionDetail,
  useBoqMutations,
  useComparison,
  useProjectBoqs,
  useRevision,
} from "./api";

const NONE = "__none";
const num = (v: string | null) => (v === null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 4 }));
const errMsg = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong");

const lineColumns: ColumnDef<BoqLine, unknown>[] = [
  { accessorKey: "line_no", header: "#", size: 56, meta: { mono: true, align: "right", exportType: "number" } },
  { accessorKey: "ref_des", header: "Ref des", size: 150, meta: { mono: true } },
  { accessorKey: "mpn", header: "MPN", size: 190, meta: { mono: true } },
  { accessorKey: "manufacturer", header: "Manufacturer", size: 150 },
  { accessorKey: "description", header: "Description", size: 230 },
  { accessorKey: "category", header: "Category", size: 110 },
  { accessorKey: "qty_per_unit", header: "Qty / unit", size: 90, meta: { mono: true, align: "right", exportType: "number", exportValue: (l: BoqLine) => Number(l.qty_per_unit) }, cell: ({ getValue }) => num(getValue() as string) },
  { accessorKey: "attrition_pct", header: "Attr. %", size: 80, meta: { mono: true, align: "right", exportType: "number", exportValue: (l: BoqLine) => Number(l.attrition_pct) }, cell: ({ row }) => <span className={cn(row.original.attrition_override && "font-semibold")}>{num(row.original.attrition_pct)}</span> },
  { accessorKey: "required_qty", header: "Required", size: 100, meta: { mono: true, align: "right", exportType: "number", exportValue: (l: BoqLine) => Number(l.required_qty) }, cell: ({ getValue }) => num(getValue() as string) },
  { accessorKey: "shortfall", header: "To order", size: 90, meta: { mono: true, align: "right", exportType: "number", exportValue: (l: BoqLine) => Number(l.shortfall) }, cell: ({ getValue }) => num(getValue() as string) },
  {
    accessorKey: "status",
    header: "Status",
    size: 150,
    cell: ({ row }) => <StatusPill tone={LINE_STATUS_TONE[row.original.status] ?? "grey"}>{row.original.dnp ? "DNP" : row.original.status}</StatusPill>,
  },
];

/* ---------------------------------------------------------------- new BOQ */

function NewBoqDialog({ open, onClose, tree, onCreated }: { open: boolean; onClose: () => void; tree: ProjectTree; onCreated: (b: Boq, importNext: boolean) => void }) {
  const { createBoq } = useBoqMutations(tree.project.id);
  const [name, setName] = React.useState("");
  const [moduleId, setModuleId] = React.useState(NONE);
  const [assemblyId, setAssemblyId] = React.useState(NONE);
  const module = tree.modules.find((m) => m.id === moduleId);
  const submit = (importNext: boolean) =>
    createBoq.mutate(
      { name: name.trim(), module_id: moduleId === NONE ? null : moduleId, assembly_id: assemblyId === NONE ? null : assemblyId, build_qty: null, create_revision: !importNext },
      { onSuccess: (b) => { toast.success(`BOQ “${b.name}” created`); onCreated(b, importNext); setName(""); }, onError: (e) => toast.error(errMsg(e)) },
    );
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title="New BOQ"
        description="A bill of quantities for the whole project, a module, or one PCB assembly."
        footer={
          <>
            <Button variant="secondary" onClick={() => submit(false)} disabled={!name.trim()} loading={createBoq.isPending}>Start empty</Button>
            <Button onClick={() => submit(true)} disabled={!name.trim()} loading={createBoq.isPending}><Upload /> Create and import file</Button>
          </>
        }
      >
        <div className="grid gap-4">
          <Field label="Name" htmlFor="boq-name" required>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Controller board BOM" />
          </Field>
          <Field label="Module" htmlFor="boq-module" hint="Build quantity defaults to the module's quantity to deliver">
            <Select value={moduleId} onValueChange={(v) => { setModuleId(v); setAssemblyId(NONE); }} options={[{ value: NONE, label: "Whole project" }, ...tree.modules.map((m) => ({ value: m.id, label: `${m.code} · ${m.name}` }))]} />
          </Field>
          {module && module.assemblies.length > 0 && (
            <Field label="PCB assembly" htmlFor="boq-assembly">
              <Select value={assemblyId} onValueChange={setAssemblyId} options={[{ value: NONE, label: "Not board-specific" }, ...module.assemblies.map((a) => ({ value: a.id, label: `${a.code} rev ${a.revision} · ${a.board_name}` }))]} />
            </Field>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- build qty and attrition */

function BuildCard({ rev, editable }: { rev: RevisionDetail; editable: boolean }) {
  const { updateBuild } = useBoqMutations("");
  const [build, setBuild] = React.useState<number | null>(rev.build_qty);
  const [rates, setRates] = React.useState<Record<string, number>>(rev.attrition_by_category);
  const [shown, setShown] = React.useState(rev.row_version);
  if (shown !== rev.row_version) {
    setShown(rev.row_version);
    setBuild(rev.build_qty);
    setRates(rev.attrition_by_category);
  }
  const dirty = build !== rev.build_qty || JSON.stringify(rates) !== JSON.stringify(rev.attrition_by_category);
  const used = new Set(rev.lines.map((l) => l.category).filter(Boolean) as string[]);
  // Only the categories this revision uses; the rest of the company defaults stay stored.
  const cats = CATEGORIES.filter((c) => used.has(c));
  return (
    <Card>
      <CardHeader title="Build quantity and attrition" description="Required = qty per unit × build quantity × (1 + attrition %), rounded up. A line's own attrition overrides its category." />
      <CardContent className="flex flex-wrap items-end gap-4">
        <Field label="Build quantity" htmlFor="rev-build">
          <NumberInput value={build} onValueChange={setBuild} unit="units" min={0} disabled={!editable} className="w-44" />
        </Field>
        {cats.map((c) => (
          <Field key={c} label={`${c} %`} htmlFor={`attr-${c}`}>
            <NumberInput value={rates[c] ?? 0} onValueChange={(v) => setRates((r) => ({ ...r, [c]: v ?? 0 }))} min={0} max={100} step={0.5} precision={1} disabled={!editable} className="w-32" />
          </Field>
        ))}
        {editable && (
          <Button
            variant="secondary"
            disabled={!dirty}
            loading={updateBuild.isPending}
            onClick={() =>
              updateBuild.mutate(
                { id: rev.id, row_version: rev.row_version, build_qty: build ?? 0, attrition_by_category: rates },
                { onSuccess: () => toast.success("Build quantity and attrition saved"), onError: (e) => toast.error(errMsg(e)) },
              )
            }
          >
            Save
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------------------------------------------------------------- compare */

const CHANGE: Record<DiffLine["change"], { label: string; tone: "green" | "red" | "amber" | "blue" | "grey"; row: string }> = {
  added: { label: "Added", tone: "green", row: "bg-status-green-bg/60" },
  removed: { label: "Removed", tone: "red", row: "bg-status-red-bg/60" },
  qty_changed: { label: "Qty changed", tone: "amber", row: "bg-status-amber-bg/60" },
  substituted: { label: "Part substituted", tone: "blue", row: "bg-status-blue-bg/60" },
  changed: { label: "Edited", tone: "grey", row: "" },
  unchanged: { label: "Unchanged", tone: "grey", row: "" },
};

const v = (l: DiffLine["from_line"], k: string) => (l && l[k] !== null && l[k] !== undefined ? String(l[k]) : "");
const qtyCell = (l: DiffLine["from_line"]) => (l ? num(String(l.qty_per_unit)) : "");

const diffColumns: ColumnDef<DiffLine, unknown>[] = [
  { id: "change", header: "Change", size: 150, accessorFn: (d) => CHANGE[d.change].label, cell: ({ row }) => <StatusPill tone={CHANGE[row.original.change].tone}>{CHANGE[row.original.change].label}</StatusPill> },
  { id: "ref", header: "Ref des", size: 150, meta: { mono: true }, accessorFn: (d) => v(d.to_line, "ref_des") || v(d.from_line, "ref_des") },
  { id: "from_mpn", header: "MPN (from)", size: 190, meta: { mono: true }, accessorFn: (d) => v(d.from_line, "mpn") },
  { id: "to_mpn", header: "MPN (to)", size: 190, meta: { mono: true }, accessorFn: (d) => v(d.to_line, "mpn") },
  { id: "from_qty", header: "Qty (from)", size: 90, meta: { mono: true, align: "right" }, accessorFn: (d) => qtyCell(d.from_line) },
  { id: "to_qty", header: "Qty (to)", size: 90, meta: { mono: true, align: "right" }, accessorFn: (d) => qtyCell(d.to_line) },
  { id: "fields", header: "Changed fields", size: 220, accessorFn: (d) => d.changed_fields.join(", ") },
  { id: "desc", header: "Description", size: 240, accessorFn: (d) => v(d.to_line, "description") || v(d.from_line, "description") },
];

export function CompareView({ boq, from, to }: { boq: Boq; from: string; to: string }) {
  const cmp = useComparison(boq.id, from, to);
  const [onlyChanges, setOnlyChanges] = React.useState(true);
  if (cmp.isPending) return <Skeleton className="h-40" />;
  if (cmp.isError) return <p role="alert" className="text-sm text-status-red-fg">{cmp.error.message}</p>;
  const lines = onlyChanges ? cmp.data.lines.filter((l) => l.change !== "unchanged") : cmp.data.lines;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" aria-label="Change summary">
        {(Object.keys(CHANGE) as DiffLine["change"][]).map((c) => (
          <StatusPill key={c} tone={CHANGE[c].tone}>
            {CHANGE[c].label}: <MonoText>{cmp.data.summary[c]}</MonoText>
          </StatusPill>
        ))}
      </div>
      <DataTable
        id="boq-compare"
        data={lines}
        columns={diffColumns}
        getRowId={(d) => d.line_key}
        exportFileName={`${boq.name}-rev-${from}-vs-${to}`}
        maxHeight={420}
        toolbar={
          <Button size="sm" variant="ghost" onClick={() => setOnlyChanges((o) => !o)}>
            {onlyChanges ? "Show unchanged lines too" : "Show changes only"}
          </Button>
        }
        emptyState={<p className="px-3 py-6 text-center text-sm text-neutral-500">The two revisions are identical.</p>}
      />
    </div>
  );
}

/* ---------------------------------------------------------------- panel */

export function BoqPanel({ tree }: { tree: ProjectTree }) {
  const projectId = tree.project.id;
  const canEdit = useCan("boq:edit");
  const canImport = useCan("boq:import");
  const canRelease = useCan("boq:release");
  const boqs = useProjectBoqs(projectId);
  const { newRevision, release, deleteRevision, saveLines, deleteBoq } = useBoqMutations(projectId);
  const [boqId, setBoqId] = React.useState<string | null>(null);
  const [revId, setRevId] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [importing, setImporting] = React.useState(false);
  const [comparing, setComparing] = React.useState<{ from: string; to: string } | null>(null);
  const [gridRows, setGridRows] = React.useState<GridRow[] | null>(null);
  const [lineErrors, setLineErrors] = React.useState<{ line: number; message: string }[]>([]);

  const boq = boqs.data?.find((b) => b.id === boqId) ?? boqs.data?.[0] ?? null;
  const revisions = boq?.revisions ?? [];
  const defaultRev = revisions.find((r) => r.status === "draft") ?? revisions.find((r) => r.status === "released") ?? revisions[revisions.length - 1];
  const summary = revisions.find((r) => r.id === revId) ?? defaultRev ?? null;
  const rev = useRevision(summary?.id ?? null);
  const editable = !!rev.data && rev.data.status === "draft" && canEdit;

  const [shownRev, setShownRev] = React.useState<string | null>(null);
  const revKey = rev.data ? `${rev.data.id}:${rev.data.row_version}` : null;
  if (revKey !== shownRev) {
    setShownRev(revKey);
    setGridRows(rev.data ? rowsFromLines(rev.data.lines) : null);
    setLineErrors([]);
  }

  if (boqs.isPending) return <Skeleton className="h-64" />;
  if (boqs.isError) return <p role="alert" className="text-sm text-status-red-fg">{boqs.error.message}</p>;

  const dirty = editable && gridRows !== null && rev.data !== undefined && JSON.stringify(rowsToInput(gridRows)) !== JSON.stringify(rowsToInput(rowsFromLines(rev.data.lines)));

  const save = () => {
    if (!rev.data || !gridRows) return;
    saveLines.mutate(
      { id: rev.data.id, row_version: rev.data.row_version, lines: rowsToInput(gridRows) },
      {
        onSuccess: () => toast.success("BOQ lines saved"),
        onError: (e) => {
          if (e instanceof ApiError && e.code === "invalid_lines" && Array.isArray(e.details)) setLineErrors(e.details as { line: number; message: string }[]);
          toast.error(errMsg(e));
        },
      },
    );
  };

  return (
    <div className="space-y-5">
      {!boqs.data.length ? (
        <Card>
          <EmptyState
            icon={ListChecks}
            title="No BOQ for this project yet"
            description="Import the client's BOQ (CSV, Excel or KiCad BOM export) or type it in."
            action={canEdit && <Button onClick={() => setCreating(true)}><Plus /> New BOQ</Button>}
          />
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="BOQ" htmlFor="boq-select">
                <Select
                  className="w-80"
                  value={boq?.id}
                  onValueChange={(id) => { setBoqId(id); setRevId(null); }}
                  options={boqs.data.map((b) => ({ value: b.id, label: [b.name, b.module_code, b.assembly_label].filter(Boolean).join(" · ") }))}
                />
              </Field>
              {revisions.length > 0 && (
                <div role="tablist" aria-label="Revisions" className="flex gap-1">
                  {revisions.map((r) => (
                    <button
                      key={r.id}
                      role="tab"
                      aria-selected={summary?.id === r.id}
                      onClick={() => setRevId(r.id)}
                      className={cn(
                        "flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-medium",
                        summary?.id === r.id ? "border-accent-600 bg-accent-50 text-accent-800" : "bg-white text-neutral-700 hover:bg-neutral-50",
                      )}
                    >
                      Rev {r.revision}
                      <StatusPill tone={REVISION_TONE[r.status]}>{r.status}</StatusPill>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {revisions.length >= 2 && (
                <Button variant="secondary" onClick={() => setComparing({ from: revisions[revisions.length - 2]?.revision ?? "A", to: revisions[revisions.length - 1]?.revision ?? "A" })}>
                  <GitCompareArrows /> Compare
                </Button>
              )}
              {canImport && boq && revisions.length > 0 && <Button variant="secondary" onClick={() => setImporting(true)}><Upload /> Import file</Button>}
              {canEdit && boq && !revisions.some((r) => r.status === "draft") && revisions.length > 0 && (
                <Button variant="secondary" loading={newRevision.isPending} onClick={() => newRevision.mutate(boq.id, { onSuccess: (r) => { setRevId(r.id); toast.success(`Revision ${r.revision} started`); }, onError: (e) => toast.error(errMsg(e)) })}>
                  <Plus /> New revision
                </Button>
              )}
              {canEdit && <Button variant="ghost" onClick={() => setCreating(true)}><Plus /> New BOQ</Button>}
            </div>
          </div>

          {boq && revisions.length === 0 && (
            <Card>
              <EmptyState
                title="This BOQ has no revision yet"
                description="Import a file to create revision A."
                action={
                  <div className="flex gap-2">
                    {canImport && <Button onClick={() => setImporting(true)}><Upload /> Import file</Button>}
                    {canEdit && <Button variant="ghost" onClick={() => deleteBoq.mutate({ id: boq.id, row_version: boq.row_version }, { onSuccess: () => toast.success("BOQ deleted"), onError: (e) => toast.error(errMsg(e)) })}><Trash2 /> Delete BOQ</Button>}
                  </div>
                }
              />
            </Card>
          )}

          {summary && rev.isPending && <Skeleton className="h-64" />}
          {rev.data && summary && (() => {
            const current = rev.data;
            return (
            <>
              <div className="flex flex-wrap items-center gap-3 text-sm text-neutral-600">
                <span>
                  Revision <MonoText className="font-semibold text-neutral-900">{rev.data.revision}</MonoText> · {rev.data.lines.length} lines
                  {rev.data.released_at && <> · released {fmtDate(rev.data.released_at)}</>}
                </span>
                {rev.data.status !== "draft" && <Badge tone="outline">Read-only: start a new revision to change it</Badge>}
                <span className="ml-auto flex gap-2">
                  {editable && (
                    <>
                      <Button variant="ghost" size="sm" onClick={() => deleteRevision.mutate({ id: current.id, row_version: current.row_version }, { onSuccess: () => { setRevId(null); toast.success("Draft deleted"); }, onError: (e) => toast.error(errMsg(e)) })}>
                        <Trash2 /> Delete draft
                      </Button>
                      <Button size="sm" variant="secondary" onClick={save} disabled={!dirty} loading={saveLines.isPending}>
                        <Save /> Save lines
                      </Button>
                    </>
                  )}
                  {rev.data.status === "draft" && canRelease && (
                    <Button
                      size="sm"
                      disabled={dirty || rev.data.lines.length === 0}
                      loading={release.isPending}
                      onClick={() => release.mutate({ id: current.id, row_version: current.row_version }, { onSuccess: (r) => toast.success(`Revision ${r.revision} released`), onError: (e) => toast.error(errMsg(e)) })}
                    >
                      <Send /> Release revision
                    </Button>
                  )}
                </span>
              </div>
              <BuildCard rev={rev.data} editable={editable} />
              {lineErrors.length > 0 && (
                <ul role="alert" className="space-y-0.5 rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">
                  {lineErrors.map((e, i) => <li key={i}>Line {e.line}: {e.message}</li>)}
                </ul>
              )}
              {editable && gridRows ? (
                <BoqGrid rows={gridRows} onChange={setGridRows} errorLines={new Set(lineErrors.map((e) => e.line))} />
              ) : (
                <DataTable id={`boq-lines-${boq?.id}`} data={rev.data.lines} columns={lineColumns} getRowId={(l) => l.id} exportFileName={`${boq?.name ?? "boq"}-rev-${rev.data.revision}`} />
              )}
            </>
            );
          })()}
        </>
      )}

      <NewBoqDialog
        open={creating}
        onClose={() => setCreating(false)}
        tree={tree}
        onCreated={(b, importNext) => {
          setCreating(false);
          setBoqId(b.id);
          setRevId(null);
          if (importNext) setImporting(true);
        }}
      />
      {boq && (
        <ImportWizard
          boqId={boq.id}
          client={tree.project.client_name}
          open={importing}
          onClose={() => setImporting(false)}
          onCommitted={(id) => {
            setImporting(false);
            setRevId(id);
          }}
        />
      )}
      {boq && comparing && (
        <Dialog open onOpenChange={(o) => !o && setComparing(null)}>
          <DialogContent size="xl" title={`Compare revisions of ${boq.name}`} description="Lines are matched by their stable line key across revisions.">
            <div className="mb-4 flex gap-3">
              <Field label="From" htmlFor="cmp-from">
                <Select className="w-32" value={comparing.from} onValueChange={(f) => setComparing((c) => c && { ...c, from: f })} options={revisions.map((r) => ({ value: r.revision, label: `Rev ${r.revision}` }))} />
              </Field>
              <Field label="To" htmlFor="cmp-to">
                <Select className="w-32" value={comparing.to} onValueChange={(t) => setComparing((c) => c && { ...c, to: t })} options={revisions.map((r) => ({ value: r.revision, label: `Rev ${r.revision}` }))} />
              </Field>
            </div>
            {comparing.from === comparing.to ? <p className="text-sm text-neutral-500">Pick two different revisions.</p> : <CompareView boq={boq} from={comparing.from} to={comparing.to} />}
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

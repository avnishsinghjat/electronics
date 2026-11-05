import type { ColumnDef } from "@tanstack/react-table";
import { ArrowRightLeft, Bookmark, Check, PackageSearch, SlidersHorizontal, X } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import {
  Button,
  Checkbox,
  Combobox,
  type ComboboxOption,
  DataTable,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  Input,
  Label,
  MonoText,
  NumberInput,
  PageHeader,
  Select,
  StatCard,
  StatusPill,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  toast,
} from "@/design/components";
import { useAuth, useCan } from "@/features/auth/AuthContext";
import { ApiError, apiGet, qs } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  type Adjustment,
  type Balance,
  LOCATION_KIND,
  type LedgerRow,
  type PartStock,
  type Reservation,
  useAdjustments,
  useBalances,
  useInventoryMutations,
  useLedger,
  useLocations,
  useReservations,
  useStock,
} from "./api";

const ALL = "__all";
const TABS = ["stock", "locations", "ledger", "adjustments", "reservations"] as const;
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");
const q4 = (v: string | number | null | undefined) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 4 }));
const isQty = (s: string) => s.trim() !== "" && !Number.isNaN(Number(s)) && Number(s) > 0;

async function loadProjects(q: string, signal: AbortSignal): Promise<ComboboxOption[]> {
  const page = await apiGet<{ items: { id: string; code: string; name: string }[] }>(`/projects${qs({ q: q || null, page_size: 50 })}`, signal);
  return page.items.map((p) => ({ value: p.id, label: p.code, description: p.name }));
}

function FormError({ error }: { error: string | null }) {
  return error ? <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">{error}</p> : null;
}

/* ---------------------------------------------------------------- dialogs */

function TransferDialog({ balance, onClose }: { balance: Balance; onClose: () => void }) {
  const locations = useLocations();
  const { transfer } = useInventoryMutations();
  const [to, setTo] = React.useState("");
  const [amount, setAmount] = React.useState("");
  const [lot, setLot] = React.useState("");
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const submit = () => {
    if (!to) return setError("Choose the destination");
    if (!isQty(amount)) return setError("Enter a positive quantity");
    transfer.mutate(
      { part_id: balance.part_id, from_location_id: balance.location_id, to_location_id: to, qty: amount.trim(), lot_code: lot.trim() || null, note: note.trim() || null },
      { onSuccess: () => { toast.success(`Moved ${amount} × ${balance.mpn}`); onClose(); }, onError: (e) => setError(errMsg(e)) },
    );
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title={`Move ${balance.mpn}`} description={`From ${balance.location_code} (${q4(balance.qty_on_hand)} on hand). Project reservations move with the stock.`}
        footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={transfer.isPending}>Move stock</Button></>}>
        <div className="grid gap-4">
          <FormError error={error} />
          <Field label="To location" htmlFor="tr-to" required>
            <Select value={to || undefined} placeholder="Choose" onValueChange={setTo} options={(locations.data ?? []).filter((l) => l.id !== balance.location_id).map((l) => ({ value: l.id, label: `${l.code} · ${LOCATION_KIND[l.kind]}` }))} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Quantity" htmlFor="tr-qty" required><Input inputMode="decimal" className="text-right font-mono" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
            <Field label="Lot" htmlFor="tr-lot"><Input className="font-mono" value={lot} onChange={(e) => setLot(e.target.value)} /></Field>
          </div>
          <Field label="Note" htmlFor="tr-note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Bake-out before reflow" /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AdjustDialog({ balance, onClose }: { balance: Balance; onClose: () => void }) {
  const { requestAdjustment } = useInventoryMutations();
  const [counted, setCounted] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const delta = counted.trim() === "" || Number.isNaN(Number(counted)) ? null : Number(counted) - Number(balance.qty_on_hand);
  const submit = () => {
    if (delta === null || Number(counted) < 0) return setError("Enter the quantity actually counted");
    if (delta === 0) return setError("The count matches the system; nothing to adjust");
    if (reason.trim().length < 3) return setError("Give the reason");
    requestAdjustment.mutate(
      { part_id: balance.part_id, location_id: balance.location_id, qty_delta: String(delta), reason: reason.trim(), lot_code: null },
      { onSuccess: () => { toast.success("Adjustment requested; it changes stock once approved"); onClose(); }, onError: (e) => setError(errMsg(e)) },
    );
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title={`Adjust ${balance.mpn} at ${balance.location_code}`} description="Requests a correction. Stock changes only when a QC Lead or Admin (not you) approves it."
        footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={requestAdjustment.isPending}>Request adjustment</Button></>}>
        <div className="grid gap-4">
          <FormError error={error} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="System quantity" htmlFor="adj-sys"><Input readOnly className="text-right font-mono" value={q4(balance.qty_on_hand)} /></Field>
            <Field label="Counted" htmlFor="adj-count" required><Input inputMode="decimal" className="text-right font-mono" value={counted} onChange={(e) => setCounted(e.target.value)} /></Field>
          </div>
          {delta !== null && delta !== 0 && <p className={cn("text-sm", delta < 0 ? "text-status-red-fg" : "text-status-green-fg")}>Change: <MonoText>{delta > 0 ? "+" : ""}{q4(delta)}</MonoText></p>}
          <Field label="Reason" htmlFor="adj-reason" required><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Cycle count, damaged in handling" /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReserveDialog({ part, onClose }: { part: PartStock; onClose: () => void }) {
  const { reserve } = useInventoryMutations();
  const [project, setProject] = React.useState<ComboboxOption | null>(null);
  const [amount, setAmount] = React.useState("");
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const submit = () => {
    if (!project) return setError("Choose the project");
    if (!isQty(amount)) return setError("Enter a positive quantity");
    reserve.mutate(
      { part_id: part.part_id, project_id: project.value, qty: amount.trim(), location_id: null, note: note.trim() || null },
      { onSuccess: () => { toast.success(`${amount} × ${part.mpn} reserved for ${project.label}`); onClose(); }, onError: (e) => setError(errMsg(e)) },
    );
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title={`Reserve ${part.mpn}`} description={`${q4(part.available)} free to reserve. Reserved stock is set aside for the project's kitting.`}
        footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={submit} loading={reserve.isPending}>Reserve</Button></>}>
        <div className="grid gap-4">
          <FormError error={error} />
          <Field label="Project" htmlFor="res-project" required><Combobox value={project} onChange={setProject} loadOptions={loadProjects} placeholder="Search projects" monoLabels /></Field>
          <Field label="Quantity" htmlFor="res-qty" required><Input inputMode="decimal" className="text-right font-mono" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
          <Field label="Note" htmlFor="res-note"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function MinStockDialog({ part, onClose }: { part: PartStock; onClose: () => void }) {
  const { setMinStock } = useInventoryMutations();
  const [min, setMin] = React.useState<number | null>(part.min_stock);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent size="sm" title={`Minimum stock for ${part.mpn}`} description="A low-stock alert shows when available stock (usable minus reserved) falls below this level."
        footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={setMinStock.isPending} onClick={() => setMinStock.mutate({ part_id: part.part_id, row_version: part.row_version, min_stock: min, msl_level: part.msl_level }, { onSuccess: () => { toast.success("Minimum stock saved"); onClose(); }, onError: (e) => toast.error(errMsg(e)) })}>Save</Button></>}>
        <Field label="Minimum stock" htmlFor="min-stock" hint="Empty = no alert"><NumberInput value={min} onValueChange={setMin} min={0} unit={part.unit} /></Field>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------------------------------------------------------- tabs */

function StockTab() {
  const [q, setQ] = React.useState("");
  const [low, setLow] = React.useState(false);
  const stock = useStock(q.trim(), low);
  const canReserve = useCan("inventory:transfer");
  const canParts = useCan("parts:manage");
  const [reserving, setReserving] = React.useState<PartStock | null>(null);
  const [minFor, setMinFor] = React.useState<PartStock | null>(null);
  const rows = stock.data ?? [];
  const columns: ColumnDef<PartStock, unknown>[] = [
    { accessorKey: "mpn", header: "MPN", size: 180, meta: { mono: true } },
    { accessorKey: "description", header: "Description", size: 220 },
    { accessorKey: "category", header: "Category", size: 100 },
    { id: "on_hand", accessorFn: (r) => Number(r.on_hand), header: "On hand", size: 92, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q4(getValue() as number) },
    { id: "usable", accessorFn: (r) => Number(r.usable), header: "Usable", size: 88, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q4(getValue() as number) },
    { id: "reserved", accessorFn: (r) => Number(r.reserved), header: "Reserved", size: 88, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q4(getValue() as number) },
    { id: "available", accessorFn: (r) => Number(r.available), header: "Available", size: 92, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => <strong>{q4(getValue() as number)}</strong> },
    { accessorKey: "min_stock", header: "Min", size: 70, meta: { mono: true, align: "right", exportType: "number" } },
    { id: "low", accessorFn: (r) => (r.low ? "Low" : ""), header: "Alert", size: 80, cell: ({ row }) => (row.original.low ? <StatusPill tone="red">Low</StatusPill> : null) },
    { id: "where", accessorFn: (r) => r.locations.join(", "), header: "Locations", size: 160, meta: { mono: true } },
    {
      id: "act",
      header: "",
      size: 90,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex gap-1">
          {canReserve && Number(row.original.available) > 0 && (
            <Button size="icon-sm" variant="ghost" aria-label={`Reserve ${row.original.mpn}`} onClick={() => setReserving(row.original)}><Bookmark /></Button>
          )}
          {canParts && (
            <Button size="icon-sm" variant="ghost" aria-label={`Minimum stock for ${row.original.mpn}`} onClick={() => setMinFor(row.original)}><SlidersHorizontal /></Button>
          )}
        </span>
      ),
    },
  ];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Parts in stock" value={rows.filter((r) => Number(r.on_hand) > 0).length} />
        <StatCard label="Low-stock alerts" value={rows.filter((r) => r.low).length} />
        <StatCard label="Parts with reservations" value={rows.filter((r) => Number(r.reserved) > 0).length} />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Search" htmlFor="stk-q" className="w-72"><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="MPN or description" /></Field>
        <div className="flex items-center gap-2 pb-2">
          <Checkbox id="stk-low" checked={low} onCheckedChange={(v) => setLow(v === true)} />
          <Label htmlFor="stk-low">Low stock only</Label>
        </div>
      </div>
      <DataTable id="stock-by-part" data={rows} columns={columns} getRowId={(r) => r.part_id} loading={stock.isPending} exportFileName="stock" emptyState={<EmptyState icon={PackageSearch} title="No stock yet" description="Stock appears here when goods are received against purchase orders." />} />
      {reserving && <ReserveDialog part={reserving} onClose={() => setReserving(null)} />}
      {minFor && <MinStockDialog part={minFor} onClose={() => setMinFor(null)} />}
    </div>
  );
}

function LocationsTab() {
  const locations = useLocations();
  const [loc, setLoc] = React.useState(ALL);
  const [q, setQ] = React.useState("");
  const balances = useBalances(q.trim(), loc === ALL ? "" : loc);
  const canMove = useCan("inventory:transfer");
  const canAdjust = useCan("inventory:adjust");
  const [moving, setMoving] = React.useState<Balance | null>(null);
  const [adjusting, setAdjusting] = React.useState<Balance | null>(null);
  const columns: ColumnDef<Balance, unknown>[] = [
    { accessorKey: "location_code", header: "Location", size: 120, meta: { mono: true } },
    { id: "kind", accessorFn: (b) => LOCATION_KIND[b.location_kind], header: "Kind", size: 140 },
    { accessorKey: "mpn", header: "MPN", size: 180, meta: { mono: true } },
    { accessorKey: "description", header: "Description", size: 240 },
    { accessorKey: "msl_level", header: "MSL", size: 60, meta: { mono: true, align: "right" } },
    { id: "qty", accessorFn: (b) => Number(b.qty_on_hand), header: "On hand", size: 100, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q4(getValue() as number) },
    {
      id: "act",
      header: "",
      size: 90,
      enableSorting: false,
      cell: ({ row }) => (
        <span className="flex gap-1">
          {canMove && <Button size="icon-sm" variant="ghost" aria-label={`Move ${row.original.mpn} from ${row.original.location_code}`} onClick={() => setMoving(row.original)}><ArrowRightLeft /></Button>}
          {canAdjust && <Button size="icon-sm" variant="ghost" aria-label={`Adjust ${row.original.mpn} at ${row.original.location_code}`} onClick={() => setAdjusting(row.original)}><SlidersHorizontal /></Button>}
        </span>
      ),
    },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Location" htmlFor="bal-loc" className="w-64">
          <Select value={loc} onValueChange={setLoc} options={[{ value: ALL, label: "All locations" }, ...(locations.data ?? []).map((l) => ({ value: l.id, label: `${l.code} · ${l.name}` }))]} />
        </Field>
        <Field label="Search" htmlFor="bal-q" className="w-72"><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="MPN or description" /></Field>
      </div>
      <DataTable id="stock-by-location" data={balances.data ?? []} columns={columns} getRowId={(b) => `${b.part_id}:${b.location_id}`} loading={balances.isPending} exportFileName="stock-by-location" />
      {moving && <TransferDialog balance={moving} onClose={() => setMoving(null)} />}
      {adjusting && <AdjustDialog balance={adjusting} onClose={() => setAdjusting(null)} />}
    </div>
  );
}

const REASON_TONE: Record<LedgerRow["reason"], "green" | "blue" | "amber" | "red" | "grey"> = { GRN: "green", ISSUE: "blue", RETURN: "green", ADJUST: "amber", SCRAP: "red", TRANSFER: "grey" };

function LedgerTab() {
  const [reason, setReason] = React.useState(ALL);
  const ledger = useLedger({ reason: reason === ALL ? undefined : reason, limit: 500 });
  const columns: ColumnDef<LedgerRow, unknown>[] = [
    { accessorKey: "id", header: "#", size: 70, meta: { mono: true, align: "right", exportType: "number" } },
    { accessorKey: "created_at", header: "When", size: 150, meta: { mono: true }, cell: ({ row }) => fmtDateTime(row.original.created_at) },
    { accessorKey: "reason", header: "Movement", size: 110, cell: ({ row }) => <StatusPill tone={REASON_TONE[row.original.reason]}>{row.original.reason}</StatusPill> },
    { accessorKey: "mpn", header: "MPN", size: 170, meta: { mono: true } },
    { accessorKey: "location_code", header: "Location", size: 110, meta: { mono: true } },
    { id: "delta", accessorFn: (r) => Number(r.qty_delta), header: "Change", size: 96, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => { const v = getValue() as number; return <span className={cn(v < 0 ? "text-status-red-fg" : "text-status-green-fg")}>{v > 0 ? "+" : ""}{q4(v)}</span>; } },
    { accessorKey: "lot_code", header: "Lot", size: 110, meta: { mono: true } },
    { accessorKey: "project_code", header: "Project", size: 130, meta: { mono: true } },
    { accessorKey: "note", header: "Note", size: 200 },
    { accessorKey: "user_name", header: "By", size: 140 },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Movement" htmlFor="led-reason" className="w-48">
          <Select value={reason} onValueChange={setReason} options={[{ value: ALL, label: "All" }, ...["GRN", "ISSUE", "RETURN", "ADJUST", "SCRAP", "TRANSFER"].map((r) => ({ value: r, label: r }))]} />
        </Field>
        <p className="pb-2 text-sm text-neutral-500">Append-only: every stock change is a row here. {ledger.data ? `${ledger.data.total} rows${ledger.data.total > 500 ? ", newest 500 shown" : ""}.` : ""}</p>
      </div>
      <DataTable id="ledger" data={ledger.data?.items ?? []} columns={columns} getRowId={(r) => String(r.id)} loading={ledger.isPending} exportFileName="inventory-ledger" />
    </div>
  );
}

function AdjustmentsTab() {
  const [status, setStatus] = React.useState("pending");
  const adjustments = useAdjustments(status === ALL ? "" : status);
  const canApprove = useCan("inventory:approve_adjustment");
  const { user } = useAuth();
  const { decideAdjustment } = useInventoryMutations();
  const decide = (a: Adjustment, approve: boolean) =>
    decideAdjustment.mutate(
      { id: a.id, row_version: a.row_version, approve, note: null },
      { onSuccess: () => toast.success(approve ? "Adjustment approved and posted" : "Adjustment rejected"), onError: (e) => toast.error(errMsg(e)) },
    );
  const columns: ColumnDef<Adjustment, unknown>[] = [
    { accessorKey: "requested_at", header: "Requested", size: 150, meta: { mono: true }, cell: ({ row }) => fmtDateTime(row.original.requested_at) },
    { accessorKey: "mpn", header: "MPN", size: 170, meta: { mono: true } },
    { accessorKey: "location_code", header: "Location", size: 110, meta: { mono: true } },
    { id: "delta", accessorFn: (a) => Number(a.qty_delta), header: "Change", size: 90, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => { const v = getValue() as number; return <span className={cn(v < 0 ? "text-status-red-fg" : "text-status-green-fg")}>{v > 0 ? "+" : ""}{q4(v)}</span>; } },
    { accessorKey: "reason", header: "Reason", size: 240 },
    { accessorKey: "requested_by_name", header: "Requested by", size: 140 },
    { accessorKey: "status", header: "Status", size: 120, cell: ({ row }) => <StatusPill tone={{ pending: "amber", approved: "green", rejected: "red" }[row.original.status] as "amber" | "green" | "red"}>{row.original.status}</StatusPill> },
    { accessorKey: "decided_by_name", header: "Decided by", size: 140 },
    {
      id: "act",
      header: "",
      size: 90,
      enableSorting: false,
      cell: ({ row }) =>
        canApprove && row.original.status === "pending" && row.original.requested_by !== user?.id ? (
          <span className="flex gap-1">
            <Button size="icon-sm" variant="ghost" aria-label={`Approve adjustment of ${row.original.mpn}`} onClick={() => decide(row.original, true)}><Check /></Button>
            <Button size="icon-sm" variant="ghost" aria-label={`Reject adjustment of ${row.original.mpn}`} onClick={() => decide(row.original, false)}><X /></Button>
          </span>
        ) : null,
    },
  ];
  return (
    <div className="space-y-4">
      <Field label="Status" htmlFor="adj-status" className="w-48">
        <Select value={status} onValueChange={setStatus} options={[{ value: "pending", label: "Pending" }, { value: "approved", label: "Approved" }, { value: "rejected", label: "Rejected" }, { value: ALL, label: "All" }]} />
      </Field>
      <DataTable id="adjustments" data={adjustments.data ?? []} columns={columns} getRowId={(a) => a.id} loading={adjustments.isPending} exportFileName="stock-adjustments" emptyState={<p className="px-3 py-6 text-center text-sm text-neutral-500">No adjustments{status === "pending" ? " waiting for approval" : ""}. Request one from the Locations tab.</p>} />
    </div>
  );
}

function ReservationsTab() {
  const reservations = useReservations();
  const canRelease = useCan("inventory:transfer");
  const { release } = useInventoryMutations();
  const columns: ColumnDef<Reservation, unknown>[] = [
    { accessorKey: "project_code", header: "Project", size: 140, meta: { mono: true } },
    { accessorKey: "mpn", header: "MPN", size: 180, meta: { mono: true } },
    { id: "qty", accessorFn: (r) => Number(r.qty), header: "Reserved", size: 100, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => q4(getValue() as number) },
    { accessorKey: "location_code", header: "Location", size: 110, meta: { mono: true } },
    { accessorKey: "note", header: "Note", size: 260 },
    { accessorKey: "created_at", header: "Since", size: 150, meta: { mono: true }, cell: ({ row }) => fmtDateTime(row.original.created_at) },
    {
      id: "act",
      header: "",
      size: 90,
      enableSorting: false,
      cell: ({ row }) =>
        canRelease && (
          <Button size="sm" variant="ghost" onClick={() => release.mutate({ id: row.original.id, row_version: row.original.row_version }, { onSuccess: () => toast.success("Reservation released"), onError: (e) => toast.error(errMsg(e)) })}>
            Release
          </Button>
        ),
    },
  ];
  return <DataTable id="reservations" data={reservations.data ?? []} columns={columns} getRowId={(r) => r.id} loading={reservations.isPending} exportFileName="reservations" emptyState={<p className="px-3 py-6 text-center text-sm text-neutral-500">No active reservations. Goods received against a project's PO are reserved for it automatically.</p>} />;
}

export default function InventoryPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") ?? "stock";
  const tab = (TABS as readonly string[]).includes(raw) ? raw : "stock";
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Inventory" }]}
        title="Inventory"
        description="Stock on hand from the append-only ledger, by part and location, with project reservations, transfers and approved adjustments."
      />
      <Tabs value={tab} onValueChange={(v) => setParams(v === "stock" ? {} : { tab: v }, { replace: true })}>
        <TabsList aria-label="Inventory sections">
          <TabsTrigger value="stock">Stock</TabsTrigger>
          <TabsTrigger value="locations">By location</TabsTrigger>
          <TabsTrigger value="ledger">Ledger</TabsTrigger>
          <TabsTrigger value="adjustments">Adjustments</TabsTrigger>
          <TabsTrigger value="reservations">Reservations</TabsTrigger>
        </TabsList>
        <TabsContent value="stock"><StockTab /></TabsContent>
        <TabsContent value="locations"><LocationsTab /></TabsContent>
        <TabsContent value="ledger"><LedgerTab /></TabsContent>
        <TabsContent value="adjustments"><AdjustmentsTab /></TabsContent>
        <TabsContent value="reservations"><ReservationsTab /></TabsContent>
      </Tabs>
    </>
  );
}

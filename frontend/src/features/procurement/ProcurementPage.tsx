import type { ColumnDef } from "@tanstack/react-table";
import { CalendarClock, Plus, Truck } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  Badge,
  Button,
  Checkbox,
  DataTable,
  DatePicker,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  Input,
  Label,
  PageHeader,
  Select,
  StatusPill,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { fmtDate, fmtDateTime, fromIsoDate, toIsoDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { PoEditor } from "./PoEditor";
import { ReturnsTable } from "./ReceiptPage";
import { VendorDrawer } from "./VendorDrawer";
import {
  PO_STATUS,
  PR_STATUS,
  type PendingLine,
  type PoStatus,
  type PurchaseOrder,
  type Receipt,
  type Requisition,
  type Vendor,
  money,
  qty,
  useOrders,
  usePending,
  useProcurementMutations,
  useReceipts,
  useRequisitions,
  useReturns,
  useVendors,
} from "./api";

const ALL = "__all";
const TABS = ["pending", "requisitions", "orders", "receipts", "returns", "vendors"] as const;
type Tab = (typeof TABS)[number];

/* ---------------------------------------------------------------- pending */

function DateDialog({ line, onClose }: { line: PendingLine; onClose: () => void }) {
  const { patchLine } = useProcurementMutations();
  const [date, setDate] = React.useState<Date | null>(fromIsoDate(line.expected_date));
  const [note, setNote] = React.useState("");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`${line.po_number} line ${line.line_no}`}
        description={`${line.mpn} from ${line.vendor_name}: record the latest promised date.`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              loading={patchLine.isPending}
              onClick={() =>
                patchLine.mutate(
                  { id: line.po_line_id, row_version: line.row_version, expected_date: toIsoDate(date), notes: note.trim() || null },
                  { onSuccess: () => { toast.success("Expected date updated"); onClose(); }, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save") },
                )
              }
            >
              Save
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <Field label="Expected delivery" htmlFor="pend-date"><DatePicker value={date} onChange={setDate} /></Field>
          <Field label="Follow-up note" htmlFor="pend-note"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PendingTab() {
  const pending = usePending();
  const canManage = useCan("po:manage");
  const [vendor, setVendor] = React.useState(ALL);
  const [overdue, setOverdue] = React.useState(false);
  const [editing, setEditing] = React.useState<PendingLine | null>(null);
  const rows = (pending.data ?? []).filter((p) => (vendor === ALL || p.vendor_id === vendor) && (!overdue || p.days_overdue > 0));
  const vendors = [...new Map((pending.data ?? []).map((p) => [p.vendor_id, p.vendor_name])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const columns: ColumnDef<PendingLine, unknown>[] = [
    { id: "expected", accessorFn: (p) => p.expected_date ?? "9999", header: "Expected", size: 110, meta: { mono: true, exportValue: (p: PendingLine) => p.expected_date ?? "" }, cell: ({ row }) => fmtDate(row.original.expected_date) },
    {
      accessorKey: "days_overdue",
      header: "Days late",
      size: 84,
      meta: { mono: true, align: "right", exportType: "number" },
      cell: ({ getValue }) => ((getValue() as number) > 0 ? <span className="font-semibold text-status-red-fg">{getValue() as number}</span> : <span className="text-neutral-400">—</span>),
    },
    { accessorKey: "po_number", header: "PO", size: 130, meta: { mono: true }, cell: ({ row }) => <Link className="font-mono text-accent-700 hover:underline" to={`/procurement/orders/${row.original.po_id}`}>{row.original.po_number}</Link> },
    { accessorKey: "line_no", header: "Line", size: 56, meta: { mono: true, align: "right" } },
    { accessorKey: "vendor_name", header: "Vendor", size: 200 },
    { accessorKey: "mpn", header: "MPN", size: 170, meta: { mono: true } },
    { accessorKey: "description", header: "Description", size: 200 },
    { id: "ordered", accessorFn: (p) => Number(p.qty_ordered), header: "Ordered", size: 84, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "received", accessorFn: (p) => Number(p.qty_received), header: "Received", size: 84, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "out", accessorFn: (p) => Number(p.outstanding), header: "Outstanding", size: 96, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => <strong>{qty(getValue() as number)}</strong> },
    { id: "value", accessorFn: (p) => (p.value_pending === null ? null : Number(p.value_pending)), header: "Value ₹", size: 100, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ row }) => money(row.original.value_pending) },
    { id: "projects", accessorFn: (p) => p.project_codes.join(", "), header: "Projects", size: 150, meta: { mono: true } },
    {
      id: "act",
      header: "",
      size: 60,
      enableSorting: false,
      cell: ({ row }) =>
        canManage && (
          <Button size="icon-sm" variant="ghost" aria-label={`Change expected date of ${row.original.po_number} line ${row.original.line_no}`} onClick={() => setEditing(row.original)}>
            <CalendarClock />
          </Button>
        ),
    },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Vendor" htmlFor="pend-vendor">
          <Select className="w-64" value={vendor} onValueChange={setVendor} options={[{ value: ALL, label: "All vendors" }, ...vendors.map(([id, name]) => ({ value: id, label: name }))]} />
        </Field>
        <div className="flex items-center gap-2 pb-2">
          <Checkbox id="pend-overdue" checked={overdue} onCheckedChange={(v) => setOverdue(v === true)} />
          <Label htmlFor="pend-overdue">Overdue only</Label>
        </div>
        <p className="ml-auto pb-2 text-sm text-neutral-500">
          {rows.filter((r) => r.days_overdue > 0).length} overdue · ₹ {money(rows.reduce((s, r) => s + Number(r.value_pending ?? 0), 0))} pending
        </p>
      </div>
      <DataTable
        id="pending-lines"
        data={rows}
        columns={columns}
        getRowId={(p) => p.po_line_id}
        loading={pending.isPending}
        error={pending.isError ? pending.error.message : null}
        exportFileName="pending-po-lines"
        emptyState={<EmptyState icon={Truck} title="Nothing outstanding" description="Every issued purchase order line is received." />}
      />
      {editing && <DateDialog line={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

/* ---------------------------------------------------------------- lists */

const prColumns: ColumnDef<Requisition, unknown>[] = [
  { accessorKey: "number", header: "Requisition", size: 140, meta: { mono: true }, cell: ({ row }) => <Link className="font-mono text-accent-700 hover:underline" to={`/procurement/requisitions/${row.original.id}`}>{row.original.number}</Link> },
  { accessorKey: "project_code", header: "Project", size: 140, meta: { mono: true } },
  { accessorKey: "project_name", header: "Project name", size: 200 },
  { accessorKey: "line_count", header: "Lines", size: 70, meta: { mono: true, align: "right", exportType: "number" } },
  { accessorKey: "created_by_name", header: "Raised by", size: 150 },
  { accessorKey: "created_at", header: "Raised", size: 150, meta: { mono: true }, cell: ({ row }) => fmtDateTime(row.original.created_at) },
  { id: "pos", accessorFn: (r) => r.purchase_orders.map((p) => p.number).join(", "), header: "Purchase orders", size: 160, meta: { mono: true } },
  { accessorKey: "status", header: "Status", size: 150, meta: { exportValue: (r: Requisition) => PR_STATUS[r.status].label }, cell: ({ row }) => <StatusPill tone={PR_STATUS[row.original.status].tone}>{PR_STATUS[row.original.status].label}</StatusPill> },
];

function RequisitionsTab() {
  const [status, setStatus] = React.useState(ALL);
  const prs = useRequisitions(status === ALL ? {} : { status });
  return (
    <div className="space-y-4">
      <Field label="Status" htmlFor="pr-status" className="w-56">
        <Select value={status} onValueChange={setStatus} options={[{ value: ALL, label: "All" }, ...(Object.keys(PR_STATUS) as Requisition["status"][]).map((s) => ({ value: s, label: PR_STATUS[s].label }))]} />
      </Field>
      <DataTable
        id="requisitions"
        data={prs.data ?? []}
        columns={prColumns}
        getRowId={(r) => r.id}
        loading={prs.isPending}
        exportFileName="requisitions"
        emptyState={<EmptyState title="No requisitions" description="Raise one from a project's Procurement tab: select lines that are short, or requisition all shortfall." />}
      />
    </div>
  );
}

const poColumns: ColumnDef<PurchaseOrder, unknown>[] = [
  { accessorKey: "number", header: "PO", size: 130, meta: { mono: true }, cell: ({ row }) => <Link className="font-mono text-accent-700 hover:underline" to={`/procurement/orders/${row.original.id}`}>{row.original.number}</Link> },
  { accessorKey: "vendor_name", header: "Vendor", size: 220 },
  { id: "projects", accessorFn: (p) => p.project_codes.join(", "), header: "Projects", size: 160, meta: { mono: true } },
  { accessorKey: "order_date", header: "Ordered", size: 110, meta: { mono: true }, cell: ({ row }) => fmtDate(row.original.order_date) },
  { accessorKey: "line_count", header: "Lines", size: 64, meta: { mono: true, align: "right", exportType: "number" } },
  { id: "total", accessorFn: (p) => Number(p.total), header: "Value ₹", size: 120, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => money(getValue() as number) },
  { accessorKey: "next_expected", header: "Next expected", size: 120, meta: { mono: true }, cell: ({ row }) => fmtDate(row.original.next_expected) },
  { accessorKey: "requisition_number", header: "From PR", size: 130, meta: { mono: true } },
  { accessorKey: "status", header: "Status", size: 150, meta: { exportValue: (p: PurchaseOrder) => PO_STATUS[p.status].label }, cell: ({ row }) => <StatusPill tone={PO_STATUS[row.original.status].tone}>{PO_STATUS[row.original.status].label}</StatusPill> },
];

function OrdersTab() {
  const [status, setStatus] = React.useState(ALL);
  const [q, setQ] = React.useState("");
  const orders = useOrders({ ...(status === ALL ? {} : { status }), ...(q.trim() ? { q: q.trim() } : {}) });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Status" htmlFor="po-status" className="w-56">
          <Select value={status} onValueChange={setStatus} options={[{ value: ALL, label: "All" }, ...(Object.keys(PO_STATUS) as PoStatus[]).map((s) => ({ value: s, label: PO_STATUS[s].label }))]} />
        </Field>
        <Field label="PO number" htmlFor="po-q" className="w-56">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. PO-2026" />
        </Field>
      </div>
      <DataTable id="purchase-orders" data={orders.data ?? []} columns={poColumns} getRowId={(p) => p.id} loading={orders.isPending} exportFileName="purchase-orders" emptyState={<EmptyState title="No purchase orders" description="Convert an approved requisition, or create an order directly." />} />
    </div>
  );
}

const grnColumns: ColumnDef<Receipt, unknown>[] = [
  { accessorKey: "number", header: "GRN", size: 140, meta: { mono: true }, cell: ({ row }) => <Link className="font-mono text-accent-700 hover:underline" to={`/procurement/receipts/${row.original.id}`}>{row.original.number}</Link> },
  { accessorKey: "received_at", header: "Received", size: 150, meta: { mono: true }, cell: ({ row }) => fmtDateTime(row.original.received_at) },
  { accessorKey: "po_number", header: "PO", size: 130, meta: { mono: true } },
  { accessorKey: "vendor_name", header: "Vendor", size: 200 },
  { accessorKey: "delivery_note_ref", header: "Delivery note", size: 140, meta: { mono: true } },
  { id: "acc", accessorFn: (g) => Number(g.qty_accepted), header: "Accepted", size: 90, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
  { id: "rej", accessorFn: (g) => Number(g.qty_rejected), header: "Rejected", size: 86, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => <span className={cn((getValue() as number) > 0 && "text-status-red-fg")}>{qty(getValue() as number)}</span> },
  { id: "hold", accessorFn: (g) => Number(g.qty_on_hold), header: "On hold", size: 80, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => <span className={cn((getValue() as number) > 0 && "text-status-amber-fg")}>{qty(getValue() as number)}</span> },
  { id: "coc", accessorFn: (g) => (g.coc_file_id ? "Yes" : "No"), header: "CoC", size: 64, cell: ({ row }) => (row.original.coc_file_id ? <Badge tone="outline">CoC</Badge> : <span className="text-neutral-400">—</span>) },
  { accessorKey: "received_by_name", header: "By", size: 140 },
];

function ReceiptsTab() {
  const grns = useReceipts();
  return <DataTable id="goods-receipts" data={grns.data ?? []} columns={grnColumns} getRowId={(g) => g.id} loading={grns.isPending} exportFileName="goods-receipts" emptyState={<EmptyState title="No goods received yet" description="Open an issued purchase order and choose Receive goods." />} />;
}

function ReturnsTab() {
  const [status, setStatus] = React.useState("open");
  const returns = useReturns(status === ALL ? "" : status);
  const canEdit = useCan("grn:create");
  return (
    <div className="space-y-4">
      <Field label="Status" htmlFor="ret-filter" className="w-56">
        <Select value={status} onValueChange={setStatus} options={[{ value: ALL, label: "All" }, { value: "open", label: "Open" }, { value: "shipped", label: "Shipped to vendor" }, { value: "credited,replaced", label: "Credited or replaced" }, { value: "closed", label: "Closed" }]} />
      </Field>
      <ReturnsTable id="vendor-returns" data={returns.data ?? []} loading={returns.isPending} canEdit={canEdit} />
    </div>
  );
}

function VendorsTab({ onOpen }: { onOpen: (v: Vendor) => void }) {
  const [q, setQ] = React.useState("");
  const vendors = useVendors(q.trim());
  const columns: ColumnDef<Vendor, unknown>[] = [
    { accessorKey: "code", header: "Code", size: 110, meta: { mono: true } },
    {
      accessorKey: "name",
      header: "Vendor",
      size: 240,
      cell: ({ row }) => (
        <button type="button" className="text-left text-accent-700 hover:underline" onClick={() => onOpen(row.original)}>
          {row.original.name}
        </button>
      ),
    },
    { accessorKey: "gstin", header: "GSTIN", size: 170, meta: { mono: true } },
    { accessorKey: "city", header: "City", size: 120 },
    { accessorKey: "payment_terms", header: "Payment terms", size: 130 },
    { accessorKey: "lead_time_days", header: "Lead time (days)", size: 120, meta: { mono: true, align: "right", exportType: "number" } },
    { id: "rating", accessorFn: (v) => (v.rating === null ? null : Number(v.rating)), header: "Rating", size: 80, meta: { mono: true, align: "right", exportType: "number" } },
    { accessorKey: "open_po_count", header: "Open POs", size: 90, meta: { mono: true, align: "right", exportType: "number" } },
    { id: "contact", accessorFn: (v) => v.contacts[0]?.phone ?? v.contacts[0]?.email ?? "", header: "Contact", size: 180 },
  ];
  return (
    <div className="space-y-4">
      <Field label="Search" htmlFor="vendor-q" className="w-72">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, code or GSTIN" />
      </Field>
      <DataTable id="vendors" data={vendors.data ?? []} columns={columns} getRowId={(v) => v.id} loading={vendors.isPending} exportFileName="vendors" />
    </div>
  );
}

/* ---------------------------------------------------------------- page */

export default function ProcurementPage() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "pending";
  const canOrder = useCan("po:manage");
  const canVendors = useCan("vendors:manage");
  const [creating, setCreating] = React.useState(false);
  const [vendor, setVendor] = React.useState<Vendor | null>(null);
  const [vendorOpen, setVendorOpen] = React.useState(false);

  const primary =
    tab === "vendors"
      ? canVendors && <Button onClick={() => { setVendor(null); setVendorOpen(true); }}><Plus /> New vendor</Button>
      : canOrder && <Button onClick={() => setCreating(true)}><Plus /> New purchase order</Button>;

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Procurement" }]}
        title="Procurement"
        description="What vendors still owe, requisitions awaiting approval, orders, receipts and returns. Requisitions are raised from a project's Procurement tab."
        primaryAction={primary}
      />
      <Tabs value={tab} onValueChange={(v) => setParams(v === "pending" ? {} : { tab: v }, { replace: true })}>
        <TabsList aria-label="Procurement sections">
          <TabsTrigger value="pending">Pending deliveries</TabsTrigger>
          <TabsTrigger value="requisitions">Requisitions</TabsTrigger>
          <TabsTrigger value="orders">Purchase orders</TabsTrigger>
          <TabsTrigger value="receipts">Goods receipts</TabsTrigger>
          <TabsTrigger value="returns">Vendor returns</TabsTrigger>
          <TabsTrigger value="vendors">Vendors</TabsTrigger>
        </TabsList>
        <TabsContent value="pending"><PendingTab /></TabsContent>
        <TabsContent value="requisitions"><RequisitionsTab /></TabsContent>
        <TabsContent value="orders"><OrdersTab /></TabsContent>
        <TabsContent value="receipts"><ReceiptsTab /></TabsContent>
        <TabsContent value="returns"><ReturnsTab /></TabsContent>
        <TabsContent value="vendors"><VendorsTab onOpen={(v) => { setVendor(v); setVendorOpen(true); }} /></TabsContent>
      </Tabs>
      <PoEditor open={creating} po={null} onClose={() => setCreating(false)} />
      <VendorDrawer open={vendorOpen} vendor={vendor} onClose={() => setVendorOpen(false)} />
    </>
  );
}

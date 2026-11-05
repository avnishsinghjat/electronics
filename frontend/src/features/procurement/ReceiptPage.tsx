import type { ColumnDef } from "@tanstack/react-table";
import { ShieldCheck } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";

import {
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
  PageHeader,
  Select,
  Skeleton,
  StatCard,
  StatusPill,
  toast,
} from "@/design/components";
import { Attachments, useAttachments } from "@/features/attachments/Attachments";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

import { INSPECTION, type GrnLine, RETURN_STATUS, type VendorReturn, qty, useProcurementMutations, useReceipt } from "./api";

const NONE = "__none";
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

function HoldDialog({ line, onClose }: { line: GrnLine; onClose: () => void }) {
  const { resolveHold } = useProcurementMutations();
  const [accept, setAccept] = React.useState(String(Number(line.qty_on_hold)));
  const [reject, setReject] = React.useState("0");
  const [reason, setReason] = React.useState("");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`Inspection decision: ${line.mpn}`}
        description={`${qty(line.qty_on_hold)} on hold. Accepted quantity goes into stock; rejected quantity is returned to the vendor.`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              loading={resolveHold.isPending}
              onClick={() =>
                resolveHold.mutate(
                  { id: line.id, row_version: line.row_version, accept_qty: accept.trim() || "0", reject_qty: reject.trim() || "0", reason: reason.trim() || null },
                  { onSuccess: () => { toast.success("Hold resolved"); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
                )
              }
            >
              Record decision
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Accept" htmlFor="hold-accept"><Input inputMode="decimal" className="text-right font-mono" value={accept} onChange={(e) => setAccept(e.target.value)} /></Field>
            <Field label="Reject" htmlFor="hold-reject"><Input inputMode="decimal" className="text-right font-mono" value={reject} onChange={(e) => setReject(e.target.value)} /></Field>
          </div>
          {Number(reject) > 0 && <Field label="Rejection reason" htmlFor="hold-reason" required><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReturnDialog({ ret, onClose }: { ret: VendorReturn; onClose: () => void }) {
  const { updateReturn } = useProcurementMutations();
  const [status, setStatus] = React.useState<VendorReturn["status"]>(ret.status);
  const [note, setNote] = React.useState("");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`Vendor return ${ret.number}`}
        description={`${qty(ret.qty)} × ${ret.mpn} to ${ret.vendor_name}`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              loading={updateReturn.isPending}
              onClick={() =>
                updateReturn.mutate(
                  { id: ret.id, row_version: ret.row_version, status, note: note.trim() || null },
                  { onSuccess: () => { toast.success("Return updated"); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
                )
              }
            >
              Save
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <Field label="Status" htmlFor="ret-status">
            <Select value={status} onValueChange={(v) => setStatus(v as VendorReturn["status"])} options={(Object.keys(RETURN_STATUS) as VendorReturn["status"][]).map((k) => ({ value: k, label: RETURN_STATUS[k].label }))} />
          </Field>
          <Field label="Note" htmlFor="ret-note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Courier docket, credit note number" /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ReturnsTable({ data, loading, canEdit, id }: { data: VendorReturn[]; loading?: boolean; canEdit: boolean; id: string }) {
  const [editing, setEditing] = React.useState<VendorReturn | null>(null);
  const columns: ColumnDef<VendorReturn, unknown>[] = [
    { accessorKey: "number", header: "Return", size: 140, meta: { mono: true } },
    { accessorKey: "vendor_name", header: "Vendor", size: 200 },
    { accessorKey: "mpn", header: "MPN", size: 170, meta: { mono: true } },
    { id: "qty", accessorFn: (r) => Number(r.qty), header: "Qty", size: 80, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { accessorKey: "reason", header: "Reason", size: 260 },
    { accessorKey: "grn_number", header: "GRN", size: 140, meta: { mono: true }, cell: ({ row }) => <Link className="font-mono text-accent-700 hover:underline" to={`/procurement/receipts/${row.original.grn_id}`}>{row.original.grn_number}</Link> },
    { accessorKey: "po_number", header: "PO", size: 130, meta: { mono: true } },
    { accessorKey: "status", header: "Status", size: 150, cell: ({ row }) => <StatusPill tone={RETURN_STATUS[row.original.status].tone}>{RETURN_STATUS[row.original.status].label}</StatusPill> },
    {
      id: "edit",
      header: "",
      size: 90,
      enableSorting: false,
      cell: ({ row }) => canEdit && row.original.status !== "closed" && <Button size="sm" variant="ghost" onClick={() => setEditing(row.original)}>Update</Button>,
    },
  ];
  return (
    <>
      <DataTable id={id} data={data} columns={columns} getRowId={(r) => r.id} loading={loading} exportFileName="vendor-returns" emptyState={<p className="px-3 py-6 text-center text-sm text-neutral-500">No vendor returns.</p>} />
      {editing && <ReturnDialog ret={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

export default function ReceiptPage() {
  const { grnId = "" } = useParams();
  const grn = useReceipt(grnId);
  const files = useAttachments("grn", grnId);
  const canReceive = useCan("grn:create");
  const { patchReceipt } = useProcurementMutations();
  const [holdLine, setHoldLine] = React.useState<GrnLine | null>(null);

  if (grn.isPending) return <Skeleton className="h-96" />;
  if (grn.isError) return <Card><EmptyState title="Goods receipt not available" description={grn.error.message} /></Card>;
  const g = grn.data;
  const coc = (files.data ?? []).find((f) => f.id === g.coc_file_id);

  const columns: ColumnDef<GrnLine, unknown>[] = [
    { accessorKey: "po_line_no", header: "PO line", size: 70, meta: { mono: true, align: "right" } },
    { accessorKey: "mpn", header: "MPN", size: 170, meta: { mono: true } },
    { accessorKey: "description", header: "Description", size: 200 },
    { id: "rcv", accessorFn: (l) => Number(l.qty_received), header: "Received", size: 86, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "acc", accessorFn: (l) => Number(l.qty_accepted), header: "Accepted", size: 86, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "rej", accessorFn: (l) => Number(l.qty_rejected), header: "Rejected", size: 80, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "hold", accessorFn: (l) => Number(l.qty_on_hold), header: "On hold", size: 76, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { accessorKey: "location_code", header: "Location", size: 100, meta: { mono: true } },
    { accessorKey: "batch_lot", header: "Lot", size: 110, meta: { mono: true } },
    { accessorKey: "date_code", header: "Date code", size: 84, meta: { mono: true } },
    { accessorKey: "msl_level", header: "MSL", size: 56, meta: { mono: true, align: "right" } },
    {
      id: "projects",
      accessorFn: (l) => l.allocated.map((a) => `${a.project_code} ${qty(a.qty)}`).join("; "),
      header: "Reserved for",
      size: 160,
      cell: ({ row }) => (row.original.allocated.length ? row.original.allocated.map((a) => <div key={a.id} className="text-xs"><MonoText>{a.project_code}</MonoText> {qty(a.qty)}</div>) : <span className="text-xs text-neutral-500">Free stock</span>),
    },
    {
      accessorKey: "inspection_result",
      header: "Inspection",
      size: 150,
      cell: ({ row }) => (
        <span className="flex items-center gap-2">
          <StatusPill tone={INSPECTION[row.original.inspection_result].tone}>{INSPECTION[row.original.inspection_result].label}</StatusPill>
          {canReceive && Number(row.original.qty_on_hold) > 0 && <Button size="sm" variant="ghost" onClick={() => setHoldLine(row.original)}>Decide</Button>}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Procurement", to: "/procurement" }, { label: "Goods receipts", to: "/procurement?tab=receipts" }, { label: g.number }]}
        title={`Goods receipt ${g.number}`}
        meta={
          <>
            <span className="text-sm text-neutral-600">{g.vendor_name}</span>
            <span className="text-sm">PO <Link to={`/procurement/orders/${g.purchase_order_id}`} className="font-mono text-accent-700 hover:underline">{g.po_number}</Link></span>
            <span className="text-sm text-neutral-500">received {fmtDateTime(g.received_at)}{g.received_by_name ? ` by ${g.received_by_name}` : ""}</span>
            {g.delivery_note_ref && <span className="text-sm text-neutral-500">DN <MonoText>{g.delivery_note_ref}</MonoText></span>}
          </>
        }
      />
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard label="Accepted into stock" value={qty(g.qty_accepted)} />
          <StatCard label="Rejected" value={qty(g.qty_rejected)} hint={g.returns.length ? `${g.returns.length} vendor return${g.returns.length === 1 ? "" : "s"}` : undefined} />
          <StatCard label="On hold" value={qty(g.qty_on_hold)} hint={Number(g.qty_on_hold) > 0 ? "awaiting an inspection decision" : undefined} />
        </div>
        <DataTable id="grn-lines" data={g.lines} columns={columns} getRowId={(l) => l.id} exportFileName={g.number} />
        <Card>
          <CardHeader title="Certificate of conformance" description="Attach the vendor's CoC and photos of the packaging and labels below, then mark which file is the CoC." />
          <CardContent className="flex flex-wrap items-end gap-3">
            <Field label="CoC document" htmlFor="grn-coc">
              <Select
                className="w-72"
                value={g.coc_file_id ?? NONE}
                disabled={!canReceive || !(files.data ?? []).length}
                onValueChange={(v) =>
                  patchReceipt.mutate(
                    { id: g.id, row_version: g.row_version, coc_file_id: v === NONE ? null : v, delivery_note_ref: g.delivery_note_ref, notes: g.notes },
                    { onSuccess: () => toast.success(v === NONE ? "CoC link removed" : "CoC linked"), onError: (e) => toast.error(errMsg(e)) },
                  )
                }
                options={[{ value: NONE, label: "Not linked" }, ...(files.data ?? []).map((f) => ({ value: f.id, label: f.original_name }))]}
              />
            </Field>
            {coc ? (
              <span className="flex items-center gap-1.5 pb-2 text-sm text-status-green-fg"><ShieldCheck className="size-4" aria-hidden="true" /> CoC on file</span>
            ) : (
              <span className="pb-2 text-sm text-status-amber-fg">No CoC linked yet</span>
            )}
          </CardContent>
        </Card>
        <Attachments refType="grn" refId={g.id} title="Receipt photos and documents" />
        {g.returns.length > 0 && (
          <section aria-label="Vendor returns" className="space-y-2">
            <h2 className="text-sm font-semibold text-neutral-800">Vendor returns</h2>
            <ReturnsTable id="grn-returns" data={g.returns} canEdit={canReceive} />
          </section>
        )}
      </div>
      {holdLine && <HoldDialog line={holdLine} onClose={() => setHoldLine(null)} />}
    </>
  );
}

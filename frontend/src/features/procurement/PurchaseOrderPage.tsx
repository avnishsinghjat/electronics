import type { ColumnDef } from "@tanstack/react-table";
import { Ban, CalendarClock, FileText, PackageCheck, Pencil, Send, Truck, XCircle } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router-dom";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  DatePicker,
  Dialog,
  DialogContent,
  EmptyState,
  Field,
  MonoText,
  PageHeader,
  Skeleton,
  StatCard,
  StatusPill,
  Textarea,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError, apiBlob } from "@/lib/api";
import { fmtDate, fmtDateTime, fromIsoDate, toIsoDate } from "@/lib/format";

import { PoEditor } from "./PoEditor";
import { ReceiveDialog } from "./ReceiveDialog";
import { PO_STATUS, type PoLine, type PurchaseOrderDetail, money, qty, useOrder, useProcurementMutations } from "./api";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

export function ConfirmDialog({ open, title, description, confirmLabel, onConfirm, onClose, busy, destructive, children }: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  busy?: boolean;
  destructive?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={title}
        description={description}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Back</Button>
            <Button variant={destructive ? "danger" : "primary"} onClick={onConfirm} loading={busy}>{confirmLabel}</Button>
          </>
        }
      >
        {children}
      </DialogContent>
    </Dialog>
  );
}

function LineDateDialog({ line, onClose }: { line: PoLine; onClose: () => void }) {
  const { patchLine } = useProcurementMutations();
  const [date, setDate] = React.useState<Date | null>(fromIsoDate(line.expected_date));
  const [notes, setNotes] = React.useState(line.notes ?? "");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`Line ${line.line_no}: ${line.mpn}`}
        description="Record the vendor's latest promised delivery date."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              loading={patchLine.isPending}
              onClick={() =>
                patchLine.mutate(
                  { id: line.id, row_version: line.row_version, expected_date: toIsoDate(date), notes: notes.trim() || null },
                  { onSuccess: () => { toast.success("Expected date updated"); onClose(); }, onError: (e) => toast.error(errMsg(e)) },
                )
              }
            >
              Save
            </Button>
          </>
        }
      >
        <div className="grid gap-4">
          <Field label="Expected delivery" htmlFor="line-date"><DatePicker value={date} onChange={setDate} /></Field>
          <Field label="Follow-up note" htmlFor="line-note"><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Confirmed by phone, ships Friday" /></Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function lineColumns(po: PurchaseOrderDetail, canManage: boolean, onDate: (l: PoLine) => void, onCancel: (l: PoLine) => void): ColumnDef<PoLine, unknown>[] {
  const open = po.status === "issued" || po.status === "partially_received";
  return [
    { accessorKey: "line_no", header: "#", size: 48, meta: { mono: true, align: "right", exportType: "number" } },
    { accessorKey: "mpn", header: "MPN", size: 170, meta: { mono: true } },
    { accessorKey: "description", header: "Description", size: 200 },
    { id: "qty", accessorFn: (l) => Number(l.qty_ordered), header: "Ordered", size: 88, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "price", accessorFn: (l) => (l.unit_price === null ? null : Number(l.unit_price)), header: "Unit ₹", size: 90, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ row }) => money(row.original.unit_price) },
    { id: "amount", accessorFn: (l) => (l.amount === null ? null : Number(l.amount)), header: "Amount ₹", size: 110, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ row }) => money(row.original.amount) },
    { accessorKey: "expected_date", header: "Expected", size: 104, meta: { mono: true }, cell: ({ row }) => fmtDate(row.original.expected_date) },
    { id: "acc", accessorFn: (l) => Number(l.qty_accepted), header: "Accepted", size: 86, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "rej", accessorFn: (l) => Number(l.qty_rejected), header: "Rejected", size: 80, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "hold", accessorFn: (l) => Number(l.qty_on_hold), header: "On hold", size: 76, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => qty(getValue() as number) },
    { id: "out", accessorFn: (l) => Number(l.outstanding), header: "Outstanding", size: 96, meta: { mono: true, align: "right", exportType: "number" }, cell: ({ getValue }) => <strong>{qty(getValue() as number)}</strong> },
    {
      id: "alloc",
      accessorFn: (l) => l.allocations.map((a) => `${a.project_code} ${qty(a.qty)}`).join("; "),
      header: "Serves",
      size: 220,
      cell: ({ row }) =>
        row.original.allocations.length ? (
          <ul className="space-y-0.5 text-xs">
            {row.original.allocations.map((a) => (
              <li key={a.id} title={a.boq_ref}>
                <Link to={`/projects/${a.project_id}?tab=procurement`} className="font-mono text-accent-700 hover:underline">{a.project_code}</Link>{" "}
                <MonoText>{qty(a.received)}/{qty(a.qty)}</MonoText>
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-xs text-neutral-500">Free stock</span>
        ),
    },
    {
      id: "actions",
      header: "",
      size: 120,
      enableSorting: false,
      meta: { exportValue: (l: PoLine) => (l.is_cancelled ? "Cancelled" : "") },
      cell: ({ row }) =>
        row.original.is_cancelled ? (
          <StatusPill tone="red">Cancelled</StatusPill>
        ) : canManage && (open || po.status === "draft") ? (
          <span className="flex gap-1">
            <Button size="icon-sm" variant="ghost" aria-label={`Change expected date of line ${row.original.line_no}`} onClick={() => onDate(row.original)}>
              <CalendarClock />
            </Button>
            {open && Number(row.original.outstanding) > 0 && (
              <Button size="icon-sm" variant="ghost" aria-label={`Cancel the remainder of line ${row.original.line_no}`} onClick={() => onCancel(row.original)}>
                <Ban />
              </Button>
            )}
          </span>
        ) : null,
    },
  ];
}

export default function PurchaseOrderPage() {
  const { poId = "" } = useParams();
  const order = useOrder(poId);
  const canManage = useCan("po:manage");
  const canReceive = useCan("grn:create");
  const { poAction, cancelLine } = useProcurementMutations();
  const [editing, setEditing] = React.useState(false);
  const [receiving, setReceiving] = React.useState(false);
  const [confirm, setConfirm] = React.useState<"issue" | "cancel" | "close" | null>(null);
  const [closeNote, setCloseNote] = React.useState("");
  const [dateLine, setDateLine] = React.useState<PoLine | null>(null);
  const [cancelling, setCancelling] = React.useState<PoLine | null>(null);

  if (order.isPending) return <Skeleton className="h-96" />;
  if (order.isError) return <Card><EmptyState title="Purchase order not available" description={order.error.message} action={<Button asChild variant="secondary"><Link to="/procurement?tab=orders">Back to purchase orders</Link></Button>} /></Card>;
  const po = order.data;
  const s = PO_STATUS[po.status];
  const receivable = po.status === "issued" || po.status === "partially_received";
  const outstanding = po.lines.reduce((n, l) => n + Number(l.outstanding), 0);

  const openPdf = async () => {
    try {
      const blob = await apiBlob(`/purchase-orders/${po.id}/pdf`);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  const act = (action: "issue" | "cancel" | "close") =>
    poAction.mutate(
      { id: po.id, action, row_version: po.row_version, note: action === "close" ? closeNote.trim() || null : null },
      {
        onSuccess: () => {
          toast.success({ issue: `${po.number} issued`, cancel: `${po.number} cancelled`, close: `${po.number} closed` }[action]);
          setConfirm(null);
        },
        onError: (e) => toast.error(errMsg(e)),
      },
    );

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Procurement", to: "/procurement" }, { label: "Purchase orders", to: "/procurement?tab=orders" }, { label: po.number }]}
        title={po.number}
        meta={
          <>
            <StatusPill tone={s.tone}>{s.label}</StatusPill>
            <span className="text-sm text-neutral-600">{po.vendor_name}</span>
            {po.requisition_id && (
              <Badge tone="outline">
                From <Link to={`/procurement/requisitions/${po.requisition_id}`} className="ml-1 font-mono text-accent-700 hover:underline">{po.requisition_number}</Link>
              </Badge>
            )}
            {po.project_codes.map((c) => <Badge key={c} tone="outline"><MonoText>{c}</MonoText></Badge>)}
          </>
        }
        secondaryActions={
          <>
            <Button variant="secondary" onClick={() => void openPdf()}><FileText /> PDF</Button>
            {canManage && po.status === "draft" && <Button variant="secondary" onClick={() => setEditing(true)}><Pencil /> Edit</Button>}
            {canManage && (po.status === "draft" || po.status === "issued") && <Button variant="ghost" onClick={() => setConfirm("cancel")}><XCircle /> Cancel order</Button>}
            {canManage && (receivable || po.status === "received") && <Button variant="ghost" onClick={() => setConfirm("close")}>Close order</Button>}
          </>
        }
        primaryAction={
          po.status === "draft" && canManage ? (
            <Button onClick={() => setConfirm("issue")}><Send /> Issue to vendor</Button>
          ) : receivable && canReceive ? (
            <Button onClick={() => setReceiving(true)}><Truck /> Receive goods</Button>
          ) : undefined
        }
      />

      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-4">
          <StatCard label="Order value" value={`₹ ${money(po.total)}`} hint="before taxes" />
          <StatCard label="Lines" value={po.line_count} hint={po.order_date ? `ordered ${fmtDate(po.order_date)}` : "not issued yet"} />
          <StatCard label="Outstanding quantity" value={qty(outstanding)} />
          <StatCard label="Next expected" value={fmtDate(po.next_expected)} />
        </div>
        <DataTable
          id="po-lines"
          data={po.lines}
          columns={lineColumns(po, canManage, setDateLine, setCancelling)}
          getRowId={(l) => l.id}
          exportFileName={po.number}
        />
        <Card>
          <CardHeader title="Goods receipts" description="Each delivery against this order." />
          <CardContent>
            {po.receipts.length ? (
              <ul className="divide-y text-sm">
                {po.receipts.map((g) => (
                  <li key={g.id} className="flex items-center gap-3 py-2">
                    <PackageCheck className="size-4 text-neutral-400" aria-hidden="true" />
                    <Link to={`/procurement/receipts/${g.id}`} className="font-mono text-accent-700 hover:underline">{g.number}</Link>
                    <span className="text-neutral-500">{fmtDateTime(g.received_at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-neutral-500">Nothing received yet.</p>
            )}
          </CardContent>
        </Card>
        {po.notes && (
          <Card>
            <CardHeader title="Notes" />
            <CardContent><p className="whitespace-pre-line text-sm text-neutral-700">{po.notes}</p></CardContent>
          </Card>
        )}
      </div>

      <PoEditor open={editing} po={po} onClose={() => setEditing(false)} />
      <ReceiveDialog po={po} open={receiving} onClose={() => setReceiving(false)} />
      {dateLine && <LineDateDialog line={dateLine} onClose={() => setDateLine(null)} />}
      <ConfirmDialog
        open={!!cancelling}
        title={`Cancel the rest of line ${cancelling?.line_no ?? ""}?`}
        description={`${qty(cancelling?.outstanding)} of ${cancelling?.mpn ?? ""} will no longer be expected from ${po.vendor_name}. What was received stays. The BOQ lines show the quantity as short again, ready to reorder.`}
        confirmLabel="Cancel remainder"
        destructive
        busy={cancelLine.isPending}
        onClose={() => setCancelling(null)}
        onConfirm={() =>
          cancelling &&
          cancelLine.mutate(
            { id: cancelling.id, row_version: cancelling.row_version },
            { onSuccess: () => { toast.success("Remainder cancelled"); setCancelling(null); }, onError: (e) => toast.error(errMsg(e)) },
          )
        }
      />
      <ConfirmDialog
        open={confirm === "issue"}
        title={`Issue ${po.number} to ${po.vendor_name}?`}
        description="The order becomes read-only and its quantities count as ordered on the BOQ tracker. Send the PDF to the vendor."
        confirmLabel="Issue order"
        busy={poAction.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => act("issue")}
      />
      <ConfirmDialog
        open={confirm === "cancel"}
        title={`Cancel ${po.number}?`}
        description="Nothing will be expected from the vendor; the BOQ lines it served show as not ordered again."
        confirmLabel="Cancel order"
        destructive
        busy={poAction.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => act("cancel")}
      />
      <ConfirmDialog
        open={confirm === "close"}
        title={`Close ${po.number}?`}
        description="Closed orders keep counting as ordered. To reorder an undelivered remainder, cancel those lines instead."
        confirmLabel="Close order"
        busy={poAction.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => act("close")}
      >
        <Field label="Reason" htmlFor="close-note"><Textarea rows={2} value={closeNote} onChange={(e) => setCloseNote(e.target.value)} /></Field>
      </ConfirmDialog>
    </>
  );
}

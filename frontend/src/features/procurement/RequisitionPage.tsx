import { Check, ShoppingCart, Trash2, X } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  EmptyState,
  Field,
  Input,
  MonoText,
  PageHeader,
  Select,
  Skeleton,
  StatusPill,
  Textarea,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

import { ConfirmDialog } from "./PurchaseOrderPage";
import { PO_STATUS, PR_STATUS, type RequisitionDetail, qty, useProcurementMutations, useRequisition, useVendors } from "./api";

const NONE = "__none";
const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

interface EditLine {
  id: string;
  boq_line_id: string | null;
  part_id: string;
  qty: string;
  vendor: string;
  notes: string | null;
}

const toEdit = (pr: RequisitionDetail): EditLine[] =>
  pr.lines.map((l) => ({ id: l.id, boq_line_id: l.boq_line_id, part_id: l.part_id, qty: String(Number(l.qty)), vendor: l.suggested_vendor_id ?? NONE, notes: l.notes }));

export default function RequisitionPage() {
  const { prId = "" } = useParams();
  const pr = useRequisition(prId);
  const vendors = useVendors();
  const navigate = useNavigate();
  const canCreate = useCan("pr:create");
  const canApprove = useCan("pr:approve");
  const canOrder = useCan("po:manage");
  const { updatePr, submitPr, decidePr, convertPr, deletePr } = useProcurementMutations();
  const [lines, setLines] = React.useState<EditLine[]>([]);
  const [shown, setShown] = React.useState<string | null>(null);
  const [deciding, setDeciding] = React.useState<"approve" | "reject" | null>(null);
  const [note, setNote] = React.useState("");
  const [deleting, setDeleting] = React.useState(false);
  const version = pr.data ? `${pr.data.id}:${pr.data.row_version}` : null;
  if (version !== shown && pr.data) {
    setShown(version);
    setLines(toEdit(pr.data));
  }

  if (pr.isPending) return <Skeleton className="h-96" />;
  if (pr.isError) return <Card><EmptyState title="Requisition not available" description={pr.error.message} /></Card>;
  const r = pr.data;
  const s = PR_STATUS[r.status];
  const editable = canCreate && (r.status === "draft" || r.status === "rejected");
  const dirty = JSON.stringify(lines) !== JSON.stringify(toEdit(r));
  const vendorOptions = [{ value: NONE, label: "— choose vendor —" }, ...(vendors.data ?? []).map((v) => ({ value: v.id, label: v.name }))];
  const missingVendor = r.lines.some((l) => !l.suggested_vendor_id);

  const save = (then?: () => void) =>
    updatePr.mutate(
      {
        id: r.id,
        row_version: r.row_version,
        notes: r.notes,
        lines: lines.map((l) => ({ boq_line_id: l.boq_line_id, part_id: l.part_id, qty: l.qty.trim(), suggested_vendor_id: l.vendor === NONE ? null : l.vendor, notes: l.notes })),
      },
      { onSuccess: () => { toast.success("Requisition saved"); then?.(); }, onError: (e) => toast.error(errMsg(e)) },
    );

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Procurement", to: "/procurement" }, { label: "Requisitions", to: "/procurement?tab=requisitions" }, { label: r.number }]}
        title={`Requisition ${r.number}`}
        meta={
          <>
            <StatusPill tone={s.tone}>{s.label}</StatusPill>
            <Badge tone="outline">
              <Link to={`/projects/${r.project_id}?tab=procurement`} className="font-mono text-accent-700 hover:underline">{r.project_code}</Link>
              <span className="ml-1">{r.project_name}</span>
            </Badge>
            <span className="text-sm text-neutral-500">raised by {r.created_by_name ?? "—"} · {fmtDateTime(r.created_at)}</span>
          </>
        }
        secondaryActions={
          editable && (
            <>
              <Button variant="ghost" onClick={() => setDeleting(true)}><Trash2 /> Delete</Button>
              <Button variant="secondary" disabled={!dirty} loading={updatePr.isPending} onClick={() => save()}>Save changes</Button>
            </>
          )
        }
        primaryAction={
          r.status === "draft" && canCreate ? (
            <Button
              disabled={dirty}
              loading={submitPr.isPending}
              onClick={() => submitPr.mutate({ id: r.id, row_version: r.row_version }, { onSuccess: () => toast.success(`${r.number} submitted for approval`), onError: (e) => toast.error(errMsg(e)) })}
            >
              Submit for approval
            </Button>
          ) : r.status === "submitted" && canApprove ? (
            <span className="flex gap-2">
              <Button variant="secondary" onClick={() => { setNote(""); setDeciding("reject"); }}><X /> Reject</Button>
              <Button onClick={() => { setNote(""); setDeciding("approve"); }}><Check /> Approve</Button>
            </span>
          ) : r.status === "approved" && canOrder ? (
            <Button
              disabled={missingVendor}
              loading={convertPr.isPending}
              onClick={() =>
                convertPr.mutate(
                  { id: r.id, row_version: r.row_version },
                  {
                    onSuccess: (orders) => {
                      toast.success(`Draft ${orders.map((o) => o.number).join(", ")} created`);
                      if (orders.length === 1 && orders[0]) navigate(`/procurement/orders/${orders[0].id}`);
                    },
                    onError: (e) => toast.error(errMsg(e)),
                  },
                )
              }
            >
              <ShoppingCart /> Create purchase orders
            </Button>
          ) : undefined
        }
      />

      <div className="space-y-5">
        {r.decision_note && (
          <p role="status" className="rounded-md border border-status-amber-border bg-status-amber-bg px-3 py-2 text-sm text-status-amber-fg">
            {r.status === "rejected" ? "Rejected" : "Approval note"}: {r.decision_note}
          </p>
        )}
        {r.status === "approved" && missingVendor && canOrder && (
          <p role="status" className="rounded-md border border-status-amber-border bg-status-amber-bg px-3 py-2 text-sm text-status-amber-fg">
            Some lines have no vendor. A requisition is turned into one purchase order per vendor, so every line needs one; ask the requester to edit and resubmit.
          </p>
        )}
        <Card>
          <CardHeader title="Lines" description={editable ? "Adjust quantities and pick the vendor for each line. Lines grouped by vendor become one PO each." : undefined} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label="Requisition lines">
              <thead className="bg-neutral-50 text-left text-xs font-semibold text-neutral-600">
                <tr>
                  <th scope="col" className="px-3 py-2">MPN</th>
                  <th scope="col" className="px-3 py-2">Description</th>
                  <th scope="col" className="px-3 py-2">For BOQ line</th>
                  <th scope="col" className="px-3 py-2 text-right">Quantity</th>
                  <th scope="col" className="px-3 py-2">Vendor</th>
                  {editable && <th scope="col" className="px-3 py-2"><span className="sr-only">Remove</span></th>}
                </tr>
              </thead>
              <tbody>
                {lines.map((e, i) => {
                  const l = r.lines.find((x) => x.id === e.id);
                  if (!l) return null;
                  return (
                    <tr key={l.id} className="h-9 border-t">
                      <td className="px-3 py-1.5 font-mono text-xs">{l.mpn}</td>
                      <td className="max-w-[18rem] truncate px-3 py-1.5 text-neutral-700">{l.description}</td>
                      <td className="px-3 py-1.5 text-xs text-neutral-600">{l.boq_ref ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right">
                        {editable ? (
                          <Input aria-label={`Quantity for ${l.mpn}`} inputMode="decimal" className="ml-auto h-8 w-24 text-right font-mono" value={e.qty} onChange={(ev) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, qty: ev.target.value } : x)))} />
                        ) : (
                          <MonoText>{qty(l.qty)} {l.unit}</MonoText>
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {editable ? (
                          <Select aria-label={`Vendor for ${l.mpn}`} className="h-8 w-56" value={e.vendor} onValueChange={(v) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, vendor: v } : x)))} options={vendorOptions} />
                        ) : (
                          l.suggested_vendor_name ?? <span className="text-status-amber-fg">No vendor</span>
                        )}
                      </td>
                      {editable && (
                        <td className="px-3 py-1.5 text-right">
                          <Button size="icon-sm" variant="ghost" aria-label={`Remove ${l.mpn}`} disabled={lines.length <= 1} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>
                            <Trash2 />
                          </Button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
        {r.purchase_orders.length > 0 && (
          <Card>
            <CardHeader title="Purchase orders" />
            <CardContent>
              <ul className="flex flex-wrap gap-3">
                {r.purchase_orders.map((o) => (
                  <li key={o.id} className="flex items-center gap-2">
                    <Link to={`/procurement/orders/${o.id}`} className="font-mono text-accent-700 hover:underline">{o.number}</Link>
                    <StatusPill tone={PO_STATUS[o.status as keyof typeof PO_STATUS]?.tone ?? "grey"}>{PO_STATUS[o.status as keyof typeof PO_STATUS]?.label ?? o.status}</StatusPill>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>

      <ConfirmDialog
        open={deciding !== null}
        title={deciding === "approve" ? `Approve ${r.number}?` : `Reject ${r.number}?`}
        description={deciding === "approve" ? "Purchase can then turn it into purchase orders." : "The requester can edit and resubmit it. The quantity is released for a new requisition."}
        confirmLabel={deciding === "approve" ? "Approve" : "Reject"}
        destructive={deciding === "reject"}
        busy={decidePr.isPending}
        onClose={() => setDeciding(null)}
        onConfirm={() => {
          if (deciding === "reject" && !note.trim()) return toast.error("Give a reason when rejecting");
          decidePr.mutate(
            { id: r.id, row_version: r.row_version, approve: deciding === "approve", note: note.trim() || null },
            { onSuccess: () => { toast.success(deciding === "approve" ? `${r.number} approved` : `${r.number} rejected`); setDeciding(null); }, onError: (e) => toast.error(errMsg(e)) },
          );
        }}
      >
        <Field label={deciding === "reject" ? "Reason" : "Note (optional)"} htmlFor="pr-note" required={deciding === "reject"}>
          <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </ConfirmDialog>
      <ConfirmDialog
        open={deleting}
        title={`Delete ${r.number}?`}
        description="The requisition is removed; its lines show as short on the tracker again."
        confirmLabel="Delete requisition"
        destructive
        busy={deletePr.isPending}
        onClose={() => setDeleting(false)}
        onConfirm={() => deletePr.mutate({ id: r.id, row_version: r.row_version }, { onSuccess: () => { toast.success("Requisition deleted"); navigate("/procurement?tab=requisitions"); }, onError: (e) => toast.error(errMsg(e)) })}
      />
    </>
  );
}

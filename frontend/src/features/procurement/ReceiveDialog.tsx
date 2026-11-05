import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Button, Dialog, DialogContent, Field, Input, MonoText, Select, toast } from "@/design/components";
import { useLocations } from "@/features/inventory/api";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { type GrnLineInput, type PurchaseOrderDetail, qty, useProcurementMutations } from "./api";

interface Row {
  received: string;
  rejected: string;
  hold: string;
  location_id: string;
  batch_lot: string;
  date_code: string;
  reject_reason: string;
}

const n = (s: string) => (s.trim() === "" ? 0 : Number(s));
const bad = (s: string) => s.trim() !== "" && (Number.isNaN(Number(s)) || Number(s) < 0);

/** Goods receipt against one purchase order: quantities per line, where it goes, lot and
 *  date code, and the incoming inspection split (accepted / rejected / on hold). */
export function ReceiveDialog({ po, open, onClose }: { po: PurchaseOrderDetail; open: boolean; onClose: () => void }) {
  const locations = useLocations(open);
  const navigate = useNavigate();
  const { receive } = useProcurementMutations();
  const openLines = po.lines.filter((l) => !l.is_cancelled && Number(l.outstanding) > 0);
  const defaultLoc = (msl: number | null) => {
    const list = locations.data ?? [];
    return (msl && msl > 1 ? list.find((l) => l.kind === "msl_cabinet") : undefined)?.id ?? list.find((l) => l.code === "STORES")?.id ?? list[0]?.id ?? "";
  };
  const [rows, setRows] = React.useState<Record<string, Row>>({});
  const [deliveryNote, setDeliveryNote] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  // The location falls back to the default until someone picks one, so typing before the
  // location list has loaded never leaves a line without a destination.
  const row = (id: string, msl: number | null): Row => {
    const r = rows[id] ?? { received: "", rejected: "", hold: "", location_id: "", batch_lot: "", date_code: "", reject_reason: "" };
    return r.location_id ? r : { ...r, location_id: defaultLoc(msl) };
  };
  const setRow = (id: string, msl: number | null, patch: Partial<Row>) => setRows((r) => ({ ...r, [id]: { ...row(id, msl), ...patch } }));

  const submit = async () => {
    setError(null);
    const problems: string[] = [];
    const lines: GrnLineInput[] = [];
    for (const l of openLines) {
      const r = row(l.id, l.msl_level);
      if (n(r.received) === 0) continue;
      if ([r.received, r.rejected, r.hold].some(bad)) problems.push(`Line ${l.line_no}: quantities must be numbers`);
      const accepted = n(r.received) - n(r.rejected) - n(r.hold);
      if (accepted < 0) problems.push(`Line ${l.line_no}: rejected + on hold exceed the quantity received`);
      if (accepted + n(r.hold) > Number(l.outstanding)) problems.push(`Line ${l.line_no}: only ${qty(l.outstanding)} is outstanding`);
      if (n(r.rejected) > 0 && !r.reject_reason.trim()) problems.push(`Line ${l.line_no}: give the reason for the rejection`);
      if (!r.location_id) problems.push(`Line ${l.line_no}: choose where it goes`);
      lines.push({
        po_line_id: l.id,
        location_id: r.location_id,
        qty_received: String(n(r.received)),
        qty_accepted: String(accepted),
        qty_rejected: String(n(r.rejected)),
        qty_on_hold: String(n(r.hold)),
        batch_lot: r.batch_lot.trim() || null,
        date_code: r.date_code.trim() || null,
        msl_level: null,
        reject_reason: r.reject_reason.trim() || null,
        notes: null,
      });
    }
    if (!lines.length) problems.push("Enter the quantity received on at least one line");
    if (problems.length) return setError(problems.join(". "));
    try {
      const grn = await receive.mutateAsync({ purchase_order_id: po.id, delivery_note_ref: deliveryNote.trim() || null, notes: null, lines });
      toast.success(`${grn.number} posted: ${qty(grn.qty_accepted)} accepted`);
      setRows({});
      setDeliveryNote("");
      onClose();
      navigate(`/procurement/receipts/${grn.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not post the receipt");
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="xl"
        title={`Receive goods on ${po.number}`}
        description={`${po.vendor_name}. Only accepted quantity goes into stock; rejected quantity creates a vendor return.`}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => void submit()} loading={receive.isPending}>Post goods receipt</Button>
          </>
        }
      >
        <div className="space-y-4">
          {error && <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">{error}</p>}
          <Field label="Vendor delivery note" htmlFor="grn-dn" className="max-w-xs">
            <Input value={deliveryNote} onChange={(e) => setDeliveryNote(e.target.value)} placeholder="e.g. DN/2026/0412" />
          </Field>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm" aria-label="Lines to receive">
              <thead className="bg-neutral-50 text-left text-xs font-semibold text-neutral-600">
                <tr>
                  <th scope="col" className="px-2 py-2">#</th>
                  <th scope="col" className="px-2 py-2">Part</th>
                  <th scope="col" className="px-2 py-2 text-right">Outstanding</th>
                  <th scope="col" className="px-2 py-2">Received</th>
                  <th scope="col" className="px-2 py-2">Rejected</th>
                  <th scope="col" className="px-2 py-2">On hold</th>
                  <th scope="col" className="px-2 py-2 text-right">Accepted</th>
                  <th scope="col" className="px-2 py-2">Location</th>
                  <th scope="col" className="px-2 py-2">Lot / batch</th>
                  <th scope="col" className="px-2 py-2">Date code</th>
                </tr>
              </thead>
              <tbody>
                {openLines.map((l) => {
                  const r = row(l.id, l.msl_level);
                  const accepted = n(r.received) - n(r.rejected) - n(r.hold);
                  const label = `line ${l.line_no}`;
                  return (
                    <React.Fragment key={l.id}>
                      <tr className="border-t align-top">
                        <td className="px-2 py-2 font-mono text-xs text-neutral-500">{l.line_no}</td>
                        <td className="px-2 py-2">
                          <MonoText className="text-xs">{l.mpn}</MonoText>
                          {l.msl_level && l.msl_level > 1 && <span className="ml-2 rounded bg-status-amber-bg px-1 text-[11px] text-status-amber-fg">MSL {l.msl_level}</span>}
                          <div className="max-w-[12rem] truncate text-xs text-neutral-500">{l.description}</div>
                        </td>
                        <td className="px-2 py-2 text-right font-mono tabular-nums">{qty(l.outstanding)}</td>
                        <td className="px-2 py-1.5"><Input aria-label={`Received, ${label}`} inputMode="decimal" className="h-8 w-16 text-right font-mono" value={r.received} onChange={(e) => setRow(l.id, l.msl_level, { received: e.target.value })} /></td>
                        <td className="px-2 py-1.5"><Input aria-label={`Rejected, ${label}`} inputMode="decimal" className="h-8 w-16 text-right font-mono" value={r.rejected} onChange={(e) => setRow(l.id, l.msl_level, { rejected: e.target.value })} /></td>
                        <td className="px-2 py-1.5"><Input aria-label={`On hold, ${label}`} inputMode="decimal" className="h-8 w-16 text-right font-mono" value={r.hold} onChange={(e) => setRow(l.id, l.msl_level, { hold: e.target.value })} /></td>
                        <td className={cn("px-2 py-2 text-right font-mono tabular-nums", accepted < 0 && "text-status-red-fg")} aria-label={`Accepted, ${label}`}>{qty(accepted)}</td>
                        <td className="px-2 py-1.5">
                          <Select aria-label={`Location, ${label}`} className="h-8 w-28" value={r.location_id || undefined} onValueChange={(v) => setRow(l.id, l.msl_level, { location_id: v })} options={(locations.data ?? []).filter((x) => x.kind !== "scrap" && x.kind !== "wip").map((x) => ({ value: x.id, label: x.code }))} />
                        </td>
                        <td className="px-2 py-1.5"><Input aria-label={`Lot, ${label}`} className="h-8 w-24 font-mono" value={r.batch_lot} onChange={(e) => setRow(l.id, l.msl_level, { batch_lot: e.target.value })} /></td>
                        <td className="px-2 py-1.5"><Input aria-label={`Date code, ${label}`} className="h-8 w-16 font-mono" value={r.date_code} onChange={(e) => setRow(l.id, l.msl_level, { date_code: e.target.value })} /></td>
                      </tr>
                      {n(r.rejected) > 0 && (
                        <tr>
                          <td />
                          <td colSpan={9} className="px-2 pb-2">
                            <Input aria-label={`Rejection reason, ${label}`} placeholder="Why was it rejected? (goes on the vendor return)" value={r.reject_reason} onChange={(e) => setRow(l.id, l.msl_level, { reject_reason: e.target.value })} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-neutral-500">Leave a line empty to skip it. Quantity on hold waits in the GRN for an inspection decision and does not count as received.</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

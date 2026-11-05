import { Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import {
  Button,
  Combobox,
  type ComboboxOption,
  DatePicker,
  Drawer,
  DrawerContent,
  Field,
  Input,
  MonoText,
  Select,
  Textarea,
  toast,
} from "@/design/components";
import { searchParts } from "@/features/boq/api";
import { ApiError, apiGet, qs } from "@/lib/api";
import { fromIsoDate, toIsoDate } from "@/lib/format";

import { type PoLineInput, type PurchaseOrderDetail, qty, useProcurementMutations, useTracker, useVendors } from "./api";

interface AllocDraft {
  key: string;
  project: ComboboxOption | null;
  boq_line_id: string;
  qty: string;
}

interface LineDraft {
  key: string;
  part: ComboboxOption | null;
  qty_ordered: string;
  unit_price: string;
  expected_date: Date | null;
  notes: string;
  allocations: AllocDraft[];
}

let seq = 0;
const nextKey = () => `k${++seq}`;
const emptyLine = (): LineDraft => ({ key: nextKey(), part: null, qty_ordered: "", unit_price: "", expected_date: null, notes: "", allocations: [] });

function fromDetail(po: PurchaseOrderDetail): LineDraft[] {
  return po.lines.map((l) => ({
    key: nextKey(),
    part: { value: l.part_id, label: l.mpn, description: l.description },
    qty_ordered: String(Number(l.qty_ordered)),
    unit_price: l.unit_price === null ? "" : String(Number(l.unit_price)),
    expected_date: fromIsoDate(l.expected_date),
    notes: l.notes ?? "",
    allocations: l.allocations.map((a) => ({
      key: nextKey(),
      project: { value: a.project_id, label: a.project_code },
      boq_line_id: a.boq_line_id,
      qty: String(Number(a.qty)),
    })),
  }));
}

async function loadParts(q: string, signal: AbortSignal): Promise<ComboboxOption[]> {
  return (await searchParts(q, signal)).map((p) => ({ value: p.id, label: p.mpn, description: [p.manufacturer, p.description].filter(Boolean).join(" · ") }));
}

async function loadProjects(q: string, signal: AbortSignal): Promise<ComboboxOption[]> {
  const page = await apiGet<{ items: { id: string; code: string; name: string }[] }>(`/projects${qs({ q: q || null, status: "draft,active,on_hold", page_size: 50 })}`, signal);
  return page.items.map((p) => ({ value: p.id, label: p.code, description: p.name }));
}

const isNum = (s: string) => s.trim() !== "" && !Number.isNaN(Number(s)) && Number(s) >= 0;

function AllocationRow({ partId, alloc, onChange, onRemove, label }: {
  partId: string | null;
  alloc: AllocDraft;
  onChange: (a: AllocDraft) => void;
  onRemove: () => void;
  label: string;
}) {
  const tracker = useTracker(alloc.project?.value ?? null);
  const lines = (tracker.data?.lines ?? []).filter((l) => l.part_id === partId);
  return (
    <div className="grid grid-cols-[11rem_minmax(0,1fr)_7rem_auto] items-start gap-2">
      <Combobox aria-label={`${label} project`} value={alloc.project} onChange={(p) => onChange({ ...alloc, project: p, boq_line_id: "" })} loadOptions={loadProjects} placeholder="Project" monoLabels />
      <Select
        aria-label={`${label} BOQ line`}
        value={alloc.boq_line_id || undefined}
        placeholder={!alloc.project ? "Pick a project first" : lines.length ? "BOQ line" : "No BOQ line for this part"}
        disabled={!alloc.project || !lines.length}
        onValueChange={(id) => {
          const l = lines.find((x) => x.boq_line_id === id);
          const open = l ? Math.max(Number(l.shortfall) - Number(l.being_ordered), 0) : 0;
          onChange({ ...alloc, boq_line_id: id, qty: alloc.qty || (open ? String(open) : "") });
        }}
        options={lines.map((l) => ({
          value: l.boq_line_id,
          label: `${l.boq_name} rev ${l.revision} line ${l.line_no}${l.ref_des ? ` (${l.ref_des.slice(0, 24)})` : ""} · short ${qty(l.shortfall)}`,
        }))}
      />
      <Input aria-label={`${label} quantity`} inputMode="decimal" className="text-right font-mono" value={alloc.qty} onChange={(e) => onChange({ ...alloc, qty: e.target.value })} />
      <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${label}`} onClick={onRemove}>
        <Trash2 />
      </Button>
    </div>
  );
}

export function PoEditor({ open, po, onClose }: { open: boolean; po: PurchaseOrderDetail | null; onClose: () => void }) {
  const vendors = useVendors();
  const navigate = useNavigate();
  const { createPo, updatePo } = useProcurementMutations();
  const [vendorId, setVendorId] = React.useState(po?.vendor_id ?? "");
  const [orderDate, setOrderDate] = React.useState<Date | null>(fromIsoDate(po?.order_date));
  const [notes, setNotes] = React.useState(po?.notes ?? "");
  const [lines, setLines] = React.useState<LineDraft[]>(po ? fromDetail(po) : [emptyLine()]);
  const [error, setError] = React.useState<string | null>(null);
  const [shownFor, setShownFor] = React.useState<string | null>(po ? `${po.id}:${po.row_version}` : null);
  const key = po ? `${po.id}:${po.row_version}` : null;
  if (key !== shownFor) {
    setShownFor(key);
    setVendorId(po?.vendor_id ?? "");
    setOrderDate(fromIsoDate(po?.order_date));
    setNotes(po?.notes ?? "");
    setLines(po ? fromDetail(po) : [emptyLine()]);
  }

  const setLine = (i: number, patch: Partial<LineDraft>) => setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const total = lines.reduce((sum, l) => (isNum(l.qty_ordered) && isNum(l.unit_price) ? sum + Number(l.qty_ordered) * Number(l.unit_price) : sum), 0);
  const busy = createPo.isPending || updatePo.isPending;

  const save = async () => {
    setError(null);
    if (!vendorId) return setError("Choose the vendor");
    const problems: string[] = [];
    const payload: PoLineInput[] = lines.map((l, i) => {
      if (!l.part) problems.push(`Line ${i + 1}: choose the part`);
      if (!isNum(l.qty_ordered) || Number(l.qty_ordered) <= 0) problems.push(`Line ${i + 1}: enter the quantity`);
      if (l.unit_price !== "" && !isNum(l.unit_price)) problems.push(`Line ${i + 1}: the unit price is not a number`);
      const allocated = l.allocations.reduce((s, a) => s + (Number(a.qty) || 0), 0);
      if (allocated > Number(l.qty_ordered)) problems.push(`Line ${i + 1}: allocations exceed the ordered quantity`);
      for (const a of l.allocations) if (!a.boq_line_id || !isNum(a.qty) || Number(a.qty) <= 0) problems.push(`Line ${i + 1}: complete or remove each allocation`);
      return {
        part_id: l.part?.value ?? "",
        qty_ordered: l.qty_ordered.trim(),
        unit_price: l.unit_price.trim() || null,
        expected_date: toIsoDate(l.expected_date),
        notes: l.notes.trim() || null,
        allocations: l.allocations.map((a) => ({ boq_line_id: a.boq_line_id, qty: a.qty.trim() })),
      };
    });
    if (problems.length) return setError([...new Set(problems)].join(". "));
    const body = { vendor_id: vendorId, order_date: toIsoDate(orderDate), notes: notes.trim() || null, lines: payload };
    try {
      const saved = po ? await updatePo.mutateAsync({ id: po.id, row_version: po.row_version, ...body }) : await createPo.mutateAsync(body);
      toast.success(po ? `${saved.number} saved` : `Draft ${saved.number} created`);
      onClose();
      if (!po) navigate(`/procurement/orders/${saved.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the order");
    }
  };

  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        width="960px"
        title={po ? `Edit ${po.number}` : "New purchase order"}
        description="Allocate each line to the BOQ lines (and projects) it serves; one line can serve several projects."
        footer={
          <>
            <span className="mr-auto text-sm text-neutral-600">
              Total before taxes <MonoText className="font-semibold text-neutral-900">₹ {total.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</MonoText>
            </span>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => void save()} loading={busy}>{po ? "Save draft" : "Create draft"}</Button>
          </>
        }
      >
        <div className="space-y-5">
          {error && <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">{error}</p>}
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_12rem]">
            <Field label="Vendor" htmlFor="po-vendor" required>
              <Select value={vendorId || undefined} placeholder="Choose a vendor" onValueChange={setVendorId} options={(vendors.data ?? []).map((v) => ({ value: v.id, label: `${v.name} (${v.code})` }))} />
            </Field>
            <Field label="Order date" htmlFor="po-date" hint="Defaults to the issue date">
              <DatePicker value={orderDate} onChange={setOrderDate} />
            </Field>
          </div>
          <ol className="space-y-4">
            {lines.map((l, i) => (
              <li key={l.key} className="rounded-lg border p-3" aria-label={`PO line ${i + 1}`}>
                <div className="grid grid-cols-[2rem_minmax(0,1.6fr)_7rem_7rem_10rem_auto] items-end gap-2">
                  <span className="pb-2 text-right font-mono text-xs text-neutral-400">{i + 1}</span>
                  <Field label="Part" htmlFor={`pl-part-${l.key}`}>
                    <Combobox value={l.part} onChange={(p) => setLine(i, { part: p, allocations: [] })} loadOptions={loadParts} placeholder="Search MPN" monoLabels />
                  </Field>
                  <Field label="Quantity" htmlFor={`pl-qty-${l.key}`}>
                    <Input inputMode="decimal" className="text-right font-mono" value={l.qty_ordered} onChange={(e) => setLine(i, { qty_ordered: e.target.value })} />
                  </Field>
                  <Field label="Unit price ₹" htmlFor={`pl-price-${l.key}`}>
                    <Input inputMode="decimal" className="text-right font-mono" value={l.unit_price} onChange={(e) => setLine(i, { unit_price: e.target.value })} />
                  </Field>
                  <Field label="Deliver by" htmlFor={`pl-date-${l.key}`}>
                    <DatePicker value={l.expected_date} onChange={(d) => setLine(i, { expected_date: d })} />
                  </Field>
                  <Button type="button" variant="ghost" size="icon" aria-label={`Remove line ${i + 1}`} disabled={lines.length === 1} onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}>
                    <Trash2 />
                  </Button>
                </div>
                <div className="ml-10 mt-3 space-y-2">
                  {l.allocations.map((a, ai) => (
                    <AllocationRow
                      key={a.key}
                      label={`line ${i + 1} allocation ${ai + 1}`}
                      partId={l.part?.value ?? null}
                      alloc={a}
                      onChange={(next) => setLine(i, { allocations: l.allocations.map((x, k) => (k === ai ? next : x)) })}
                      onRemove={() => setLine(i, { allocations: l.allocations.filter((_, k) => k !== ai) })}
                    />
                  ))}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={!l.part}
                    onClick={() => setLine(i, { allocations: [...l.allocations, { key: nextKey(), project: null, boq_line_id: "", qty: "" }] })}
                  >
                    <Plus /> Allocate to a BOQ line
                  </Button>
                  {!l.allocations.length && l.part && <span className="ml-2 text-xs text-neutral-500">Unallocated quantity becomes free stock.</span>}
                </div>
              </li>
            ))}
          </ol>
          <Button type="button" variant="secondary" onClick={() => setLines((ls) => [...ls, emptyLine()])}>
            <Plus /> Add line
          </Button>
          <Field label="Notes" htmlFor="po-notes" hint="Printed on the PO">
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
        </div>
      </DrawerContent>
    </Drawer>
  );
}

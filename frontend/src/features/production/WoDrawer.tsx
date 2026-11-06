import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Button, Checkbox, Combobox, type ComboboxOption, DatePicker, Drawer, DrawerContent, Field, Label, NumberInput, Select, Textarea, toast } from "@/design/components";
import { useProjectBoqs } from "@/features/boq/api";
import { useProjectTree } from "@/features/projects/api";
import { ApiError, apiGet, qs } from "@/lib/api";
import { fromIsoDate, toIsoDate } from "@/lib/format";

import { type WorkOrderDetail, useProductionMutations } from "./api";

const AUTO = "__auto";

async function loadProjects(q: string, signal: AbortSignal): Promise<ComboboxOption[]> {
  const page = await apiGet<{ items: { id: string; code: string; name: string }[] }>(`/projects${qs({ q: q || null, status: "draft,active,on_hold", page_size: 50 })}`, signal);
  return page.items.map((p) => ({ value: p.id, label: p.code, description: p.name }));
}

/** New work order (pick the project and board) or edit a planned one. */
export function WoDrawer({ open, onClose, wo, project }: { open: boolean; onClose: () => void; wo?: WorkOrderDetail | null; project?: ComboboxOption | null }) {
  const navigate = useNavigate();
  const { createWo, updateWo } = useProductionMutations();
  const [proj, setProj] = React.useState<ComboboxOption | null>(project ?? null);
  const [assemblyId, setAssemblyId] = React.useState("");
  const [buildQty, setBuildQty] = React.useState<number | null>(wo?.build_qty ?? null);
  const [start, setStart] = React.useState<Date | null>(fromIsoDate(wo?.planned_start));
  const [end, setEnd] = React.useState<Date | null>(fromIsoDate(wo?.planned_end));
  const [serials, setSerials] = React.useState(wo?.track_serials ?? true);
  const [boqId, setBoqId] = React.useState(wo?.boq_id ?? AUTO);
  const [notes, setNotes] = React.useState(wo?.notes ?? "");
  const [error, setError] = React.useState<string | null>(null);
  const projectId = wo?.project_id ?? proj?.value ?? null;
  const tree = useProjectTree(open && !wo ? projectId : null);
  const boqs = useProjectBoqs(projectId ?? "");
  const assemblies = (tree.data?.modules ?? []).flatMap((m) =>
    m.assemblies.map((a) => ({ value: a.id, label: `${m.code} · ${a.code} rev ${a.revision} · ${a.board_name}`, qty: m.qty_to_deliver })),
  );

  const save = async () => {
    setError(null);
    if (!wo && !assemblyId) return setError("Choose the PCB assembly to build");
    if (!buildQty || buildQty < 1) return setError("Enter the build quantity");
    const body = {
      build_qty: buildQty,
      planned_start: toIsoDate(start),
      planned_end: toIsoDate(end),
      track_serials: serials,
      boq_id: boqId === AUTO ? null : boqId,
      notes: notes.trim() || null,
    };
    try {
      if (wo) {
        await updateWo.mutateAsync({ id: wo.id, row_version: wo.row_version, ...body });
        toast.success(`${wo.number} saved`);
        onClose();
      } else {
        const created = await createWo.mutateAsync({ assembly_id: assemblyId, ...body });
        toast.success(`Work order ${created.number} created with lot ${created.lot_number ?? ""}`);
        onClose();
        navigate(`/production/work-orders/${created.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the work order");
    }
  };

  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        width="560px"
        title={wo ? `Edit ${wo.number}` : "New work order"}
        description={wo ? wo.assembly_label : "Builds one PCB assembly as one lot. Stages are copied from the assembly's stage template."}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => void save()} loading={createWo.isPending || updateWo.isPending}>{wo ? "Save" : "Create work order"}</Button>
          </>
        }
      >
        <div className="grid gap-4">
          {error && <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">{error}</p>}
          {!wo && (
            <>
              <Field label="Project" htmlFor="wo-project" required>
                <Combobox value={proj} onChange={(p) => { setProj(p); setAssemblyId(""); setBoqId(AUTO); }} loadOptions={loadProjects} placeholder="Search projects" monoLabels />
              </Field>
              <Field label="PCB assembly" htmlFor="wo-assembly" required>
                <Select
                  value={assemblyId || undefined}
                  placeholder={!proj ? "Pick a project first" : assemblies.length ? "Choose the board" : "This project has no assemblies"}
                  disabled={!assemblies.length}
                  onValueChange={(v) => {
                    setAssemblyId(v);
                    if (buildQty === null) setBuildQty(assemblies.find((a) => a.value === v)?.qty ?? null);
                  }}
                  options={assemblies.map(({ value, label }) => ({ value, label }))}
                />
              </Field>
            </>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Build quantity" htmlFor="wo-qty" required>
              <NumberInput value={buildQty} onValueChange={setBuildQty} min={1} unit="boards" />
            </Field>
            <Field label="BOQ to kit from" htmlFor="wo-boq" hint="Automatic: the board's BOQ, else the module's">
              <Select value={boqId} onValueChange={setBoqId} options={[{ value: AUTO, label: "Automatic" }, ...(boqs.data ?? []).map((b) => ({ value: b.id, label: [b.name, b.module_code, b.assembly_label].filter(Boolean).join(" · ") }))]} />
            </Field>
            <Field label="Planned start" htmlFor="wo-start"><DatePicker value={start} onChange={setStart} /></Field>
            <Field label="Planned end" htmlFor="wo-end"><DatePicker value={end} onChange={setEnd} /></Field>
          </div>
          <div className="flex items-start gap-2">
            <Checkbox id="wo-serials" checked={serials} onCheckedChange={(v) => setSerials(v === true)} />
            <div>
              <Label htmlFor="wo-serials">Track each board by serial number</Label>
              <p className="text-xs text-neutral-500">Untick for low-value boards tracked by lot only.</p>
            </div>
          </div>
          <Field label="Notes" htmlFor="wo-notes"><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        </div>
      </DrawerContent>
    </Drawer>
  );
}

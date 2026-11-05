import { zodResolver } from "@hookform/resolvers/zod";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Drawer, DrawerContent, Field, Input, NumberInput, Select, Textarea, toast } from "@/design/components";
import { Attachments, useAttachments } from "@/features/attachments/Attachments";
import { ApiError } from "@/lib/api";

import { type Assembly, type Module, useOrgMutations, useStageTemplates } from "./api";

const CODE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/;
const NONE = "__none";

/* ---------------------------------------------------------------- module */

const moduleSchema = z.object({
  code: z.string().trim().regex(CODE, "1-32 letters, digits, dot, dash or underscore"),
  name: z.string().trim().min(1, "Enter the module name").max(200),
  qty_to_deliver: z.number({ invalid_type_error: "Enter a quantity" }).int().min(0, "Cannot be negative"),
  description: z.string().max(2000),
});

export function ModuleDrawer({ open, projectId, module, onClose }: { open: boolean; projectId: string; module: Module | null; onClose: () => void }) {
  const { createModule, updateModule } = useOrgMutations();
  const form = useForm<z.infer<typeof moduleSchema>>({
    resolver: zodResolver(moduleSchema),
    values: { code: module?.code ?? "", name: module?.name ?? "", qty_to_deliver: module?.qty_to_deliver ?? 1, description: module?.description ?? "" },
  });
  const submit = form.handleSubmit(async (v) => {
    const body = { ...v, description: v.description || null };
    try {
      if (module) await updateModule.mutateAsync({ id: module.id, row_version: module.row_version, ...body });
      else await createModule.mutateAsync({ projectId, ...body });
      toast.success(module ? "Module saved" : `Module ${v.code} added`);
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save");
    }
  });
  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        title={module ? `Edit module ${module.code}` : "New module"}
        description="A deliverable unit of the project, e.g. “Controller module ×50”."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => void submit()} loading={form.formState.isSubmitting}>{module ? "Save module" : "Add module"}</Button>
          </>
        }
      >
        <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
          <Field label="Code" htmlFor="m-code" error={form.formState.errors.code?.message} required>
            <Input className="font-mono" {...form.register("code")} />
          </Field>
          <Field label="Quantity to deliver" htmlFor="m-qty" error={form.formState.errors.qty_to_deliver?.message} required>
            <Controller control={form.control} name="qty_to_deliver" render={({ field }) => (
              <NumberInput value={field.value} onValueChange={(v) => field.onChange(v ?? 0)} unit="units" min={0} />
            )} />
          </Field>
          <Field label="Name" htmlFor="m-name" className="sm:col-span-2" error={form.formState.errors.name?.message} required>
            <Input {...form.register("name")} />
          </Field>
          <Field label="Description" htmlFor="m-desc" className="sm:col-span-2">
            <Textarea rows={3} {...form.register("description")} />
          </Field>
        </form>
      </DrawerContent>
    </Drawer>
  );
}

/* ---------------------------------------------------------------- assembly */

const decimalText = z.string().trim().refine((v) => v === "" || (/^\d+(\.\d{1,2})?$/.test(v) && Number(v) > 0), "Positive number, up to 2 decimals");

const assemblySchema = z.object({
  code: z.string().trim().regex(CODE, "1-32 letters, digits, dot, dash or underscore"),
  board_name: z.string().trim().min(1, "Enter the board name").max(200),
  revision: z.string().trim().min(1, "Enter the revision").max(16),
  qty_per_module: z.number().int().min(1).max(1000),
  layer_count: z.number().int().min(1, "1 to 64 layers").max(64, "1 to 64 layers"),
  size_x_mm: decimalText,
  size_y_mm: decimalText,
  finish: z.string().max(64),
  stage_template_id: z.string(),
  notes: z.string().max(5000),
  assembly_drawing_file_id: z.string(),
  kicad_project_file_id: z.string(),
});
type AssemblyForm = z.infer<typeof assemblySchema>;

const FINISHES = ["ENIG", "HASL lead-free", "HASL", "OSP", "Immersion silver", "Immersion tin", "ENEPIG"];

export function AssemblyDrawer({ open, moduleId, assembly, onClose }: { open: boolean; moduleId: string; assembly: Assembly | null; onClose: () => void }) {
  const { createAssembly, updateAssembly } = useOrgMutations();
  const templates = useStageTemplates();
  const files = useAttachments("assembly", open && assembly ? assembly.id : null);
  const form = useForm<AssemblyForm>({
    resolver: zodResolver(assemblySchema),
    values: {
      code: assembly?.code ?? "",
      board_name: assembly?.board_name ?? "",
      revision: assembly?.revision ?? "A",
      qty_per_module: assembly?.qty_per_module ?? 1,
      layer_count: assembly?.layer_count ?? 2,
      size_x_mm: assembly?.size_x_mm ?? "",
      size_y_mm: assembly?.size_y_mm ?? "",
      finish: assembly?.finish ?? "",
      stage_template_id: assembly?.stage_template_id ?? "",
      notes: assembly?.notes ?? "",
      assembly_drawing_file_id: assembly?.assembly_drawing_file_id ?? "",
      kicad_project_file_id: assembly?.kicad_project_file_id ?? "",
    },
  });
  const fileOptions = [{ value: NONE, label: "None" }, ...(assembly ? (files.data ?? []).map((f) => ({ value: f.id, label: f.original_name })) : [])];

  const submit = form.handleSubmit(async (v) => {
    const body = {
      code: v.code,
      board_name: v.board_name,
      revision: v.revision,
      qty_per_module: v.qty_per_module,
      layer_count: v.layer_count,
      size_x_mm: v.size_x_mm || null,
      size_y_mm: v.size_y_mm || null,
      finish: v.finish || null,
      stage_template_id: v.stage_template_id || null,
      notes: v.notes || null,
    };
    try {
      if (assembly) {
        await updateAssembly.mutateAsync({
          id: assembly.id,
          row_version: assembly.row_version,
          ...body,
          assembly_drawing_file_id: v.assembly_drawing_file_id || null,
          kicad_project_file_id: v.kicad_project_file_id || null,
        });
      } else {
        await createAssembly.mutateAsync({ moduleId, ...body });
      }
      toast.success(assembly ? "Assembly saved" : `Assembly ${v.code} rev ${v.revision} added`);
      onClose();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save");
    }
  });

  const numberField = (name: "qty_per_module" | "layer_count", label: string, unit: string, min: number, max: number) => (
    <Field label={label} htmlFor={`a-${name}`} error={form.formState.errors[name]?.message} required>
      <Controller control={form.control} name={name} render={({ field }) => (
        <NumberInput value={field.value} onValueChange={(v) => field.onChange(v ?? min)} unit={unit} min={min} max={max} />
      )} />
    </Field>
  );

  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        width="640px"
        title={assembly ? `Edit ${assembly.code} rev ${assembly.revision}` : "New PCB assembly"}
        description="A board revision used in this module."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={() => void submit()} loading={form.formState.isSubmitting}>{assembly ? "Save assembly" : "Add assembly"}</Button>
          </>
        }
      >
        <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-3">
          <Field label="Assembly code" htmlFor="a-code" hint="Used in serial numbers" error={form.formState.errors.code?.message} required>
            <Input className="font-mono" {...form.register("code")} />
          </Field>
          <Field label="Revision" htmlFor="a-revision" error={form.formState.errors.revision?.message} required>
            <Input className="font-mono" {...form.register("revision")} />
          </Field>
          {numberField("qty_per_module", "Boards per module", "pcs", 1, 1000)}
          <Field label="Board name" htmlFor="a-board" className="sm:col-span-3" error={form.formState.errors.board_name?.message} required>
            <Input {...form.register("board_name")} />
          </Field>
          {numberField("layer_count", "Layers", "layers", 1, 64)}
          <Field label="Width" htmlFor="a-x" hint="mm" error={form.formState.errors.size_x_mm?.message}>
            <Input inputMode="decimal" className="font-mono" {...form.register("size_x_mm")} />
          </Field>
          <Field label="Height" htmlFor="a-y" hint="mm" error={form.formState.errors.size_y_mm?.message}>
            <Input inputMode="decimal" className="font-mono" {...form.register("size_y_mm")} />
          </Field>
          <Field label="Surface finish" htmlFor="a-finish">
            <Controller control={form.control} name="finish" render={({ field }) => (
              <Select value={field.value || NONE} onValueChange={(v) => field.onChange(v === NONE ? "" : v)} options={[{ value: NONE, label: "Not specified" }, ...FINISHES.map((f) => ({ value: f, label: f }))]} />
            )} />
          </Field>
          <Field label="Production stages" htmlFor="a-template" className="sm:col-span-2" hint="Stage list used by work orders (Phase 7)">
            <Controller control={form.control} name="stage_template_id" render={({ field }) => (
              <Select value={field.value || undefined} onValueChange={field.onChange} placeholder="Default template" options={(templates.data ?? []).map((t) => ({ value: t.id, label: t.is_default ? `${t.name} (default)` : t.name }))} />
            )} />
          </Field>
          {assembly && (
            <>
              <Field label="Assembly drawing" htmlFor="a-drawing" className="sm:col-span-3" hint="Pick from the files attached below">
                <Controller control={form.control} name="assembly_drawing_file_id" render={({ field }) => (
                  <Select value={field.value || NONE} onValueChange={(v) => field.onChange(v === NONE ? "" : v)} options={fileOptions} />
                )} />
              </Field>
              <Field label="KiCad project" htmlFor="a-kicad" className="sm:col-span-3" hint="Zipped KiCad project; analysed in the Design Lab (Phase 12)">
                <Controller control={form.control} name="kicad_project_file_id" render={({ field }) => (
                  <Select value={field.value || NONE} onValueChange={(v) => field.onChange(v === NONE ? "" : v)} options={fileOptions} />
                )} />
              </Field>
            </>
          )}
          <Field label="Notes" htmlFor="a-notes" className="sm:col-span-3">
            <Textarea rows={2} {...form.register("notes")} />
          </Field>
        </form>
        <div className="mt-6 border-t pt-4">
          <h3 className="mb-3 text-sm font-semibold text-neutral-900">Assembly files</h3>
          {assembly ? (
            <Attachments refType="assembly" refId={assembly.id} title="Assembly files" />
          ) : (
            <p className="text-sm text-neutral-500">Save the assembly first, then attach its drawing, Gerbers and KiCad project.</p>
          )}
        </div>
      </DrawerContent>
    </Drawer>
  );
}

export function useStructureDrawers() {
  const [moduleDrawer, setModuleDrawer] = React.useState<{ module: Module | null } | null>(null);
  const [assemblyDrawer, setAssemblyDrawer] = React.useState<{ moduleId: string; assembly: Assembly | null } | null>(null);
  return { moduleDrawer, setModuleDrawer, assemblyDrawer, setAssemblyDrawer };
}

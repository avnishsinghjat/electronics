import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import {
  Button,
  Checkbox,
  DatePicker,
  Dialog,
  DialogContent,
  Drawer,
  DrawerContent,
  Field,
  Input,
  Label,
  MonoText,
  Select,
  Textarea,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { fromIsoDate, toIsoDate } from "@/lib/format";

import { type Division, PROJECT_STATUSES, type Project, type ProjectStatus, useDivisionsQuery, useOrgMutations, useStaff } from "./api";

const NONE = "__none";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong";
}

/* ---------------------------------------------------------------- project create / edit */

const projectSchema = z
  .object({
    division_id: z.string().min(1, "Pick a division"),
    name: z.string().trim().min(1, "Enter the project name").max(200),
    client_name: z.string().trim().min(1, "Enter the client").max(200),
    client_po_ref: z.string().max(100),
    start_date: z.date().nullable(),
    due_date: z.date().nullable(),
    status: z.enum(["draft", "active", "on_hold", "completed", "cancelled"]),
    project_manager_id: z.string(),
    notes: z.string().max(5000),
  })
  .refine((v) => !v.start_date || !v.due_date || v.due_date >= v.start_date, { path: ["due_date"], message: "Due date is before the start date" });
type ProjectForm = z.infer<typeof projectSchema>;

export function ProjectDrawer({ open, project, defaultDivisionId, onClose, onSaved }: {
  open: boolean;
  project: Project | null;
  defaultDivisionId?: string | null;
  onClose: () => void;
  onSaved?: (p: Project) => void;
}) {
  const divisions = useDivisionsQuery();
  const staff = useStaff(open);
  const { createProject, updateProject } = useOrgMutations();
  const [error, setError] = React.useState<string | null>(null);
  const form = useForm<ProjectForm>({
    resolver: zodResolver(projectSchema),
    values: {
      division_id: project?.division_id ?? defaultDivisionId ?? divisions.data?.[0]?.id ?? "",
      name: project?.name ?? "",
      client_name: project?.client_name ?? "",
      client_po_ref: project?.client_po_ref ?? "",
      start_date: fromIsoDate(project?.start_date),
      due_date: fromIsoDate(project?.due_date),
      status: project?.status ?? "draft",
      project_manager_id: project?.project_manager_id ?? "",
      notes: project?.notes ?? "",
    },
  });
  const managers = (staff.data ?? []).filter((u) => u.roles.includes("project_manager") || u.roles.includes("admin"));

  const submit = form.handleSubmit(async (v) => {
    setError(null);
    const body = {
      division_id: v.division_id,
      name: v.name,
      client_name: v.client_name,
      client_po_ref: v.client_po_ref || null,
      start_date: toIsoDate(v.start_date),
      due_date: toIsoDate(v.due_date),
      status: v.status as ProjectStatus,
      project_manager_id: v.project_manager_id || null,
      notes: v.notes || null,
    };
    try {
      const saved = project
        ? await updateProject.mutateAsync({ id: project.id, row_version: project.row_version, ...body })
        : await createProject.mutateAsync(body);
      toast.success(project ? "Project saved" : `Project ${saved.code} created`);
      onSaved?.(saved as Project);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  });

  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        width="560px"
        title={project ? `Edit ${project.code}` : "New project"}
        description={project ? undefined : "The project number is assigned automatically."}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => void submit()} loading={form.formState.isSubmitting}>
              {project ? "Save project" : "Create project"}
            </Button>
          </>
        }
      >
        <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
          {error && (
            <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg sm:col-span-2">
              {error}
            </p>
          )}
          <Field label="Project name" htmlFor="p-name" className="sm:col-span-2" error={form.formState.errors.name?.message} required>
            <Input {...form.register("name")} />
          </Field>
          <Field label="Client" htmlFor="p-client" error={form.formState.errors.client_name?.message} required>
            <Input {...form.register("client_name")} />
          </Field>
          <Field label="Client PO reference" htmlFor="p-po" error={form.formState.errors.client_po_ref?.message}>
            <Input className="font-mono" {...form.register("client_po_ref")} />
          </Field>
          <Field label="Division" htmlFor="p-division" error={form.formState.errors.division_id?.message} required>
            <Controller control={form.control} name="division_id" render={({ field }) => (
              <Select value={field.value || undefined} onValueChange={field.onChange} options={(divisions.data ?? []).map((d) => ({ value: d.id, label: d.name }))} />
            )} />
          </Field>
          <Field label="Status" htmlFor="p-status">
            <Controller control={form.control} name="status" render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange} options={PROJECT_STATUSES.map((s) => ({ value: s.value, label: s.label }))} />
            )} />
          </Field>
          <Field label="Start date" htmlFor="p-start" error={form.formState.errors.start_date?.message}>
            <Controller control={form.control} name="start_date" render={({ field }) => <DatePicker value={field.value} onChange={field.onChange} />} />
          </Field>
          <Field label="Due date" htmlFor="p-due" error={form.formState.errors.due_date?.message}>
            <Controller control={form.control} name="due_date" render={({ field }) => <DatePicker value={field.value} onChange={field.onChange} />} />
          </Field>
          <Field label="Project manager" htmlFor="p-pm" className="sm:col-span-2" hint={staff.isError ? "Staff list unavailable" : undefined}>
            <Controller control={form.control} name="project_manager_id" render={({ field }) => (
              <Select
                value={field.value || NONE}
                onValueChange={(v) => field.onChange(v === NONE ? "" : v)}
                options={[{ value: NONE, label: "Not assigned" }, ...managers.map((u) => ({ value: u.id, label: u.full_name }))]}
              />
            )} />
          </Field>
          <Field label="Notes" htmlFor="p-notes" className="sm:col-span-2">
            <Textarea rows={3} {...form.register("notes")} />
          </Field>
        </form>
      </DrawerContent>
    </Drawer>
  );
}

/* ---------------------------------------------------------------- divisions */

const divisionSchema = z.object({
  code: z.string().trim().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/, "1-32 letters, digits, dot, dash or underscore"),
  name: z.string().trim().min(1, "Enter the name").max(200),
  description: z.string().max(2000),
});

function DivisionForm({ division, onDone }: { division: Division | null; onDone: () => void }) {
  const { createDivision, updateDivision } = useOrgMutations();
  const form = useForm<z.infer<typeof divisionSchema>>({
    resolver: zodResolver(divisionSchema),
    values: { code: division?.code ?? "", name: division?.name ?? "", description: division?.description ?? "" },
  });
  const submit = form.handleSubmit(async (v) => {
    try {
      const body = { code: v.code, name: v.name, description: v.description || null };
      if (division) await updateDivision.mutateAsync({ id: division.id, row_version: division.row_version, ...body });
      else await createDivision.mutateAsync(body);
      toast.success(division ? "Division saved" : "Division created");
      onDone();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  });
  return (
    <form onSubmit={submit} noValidate className="grid gap-3 rounded-md border bg-neutral-25 p-3 sm:grid-cols-[120px_1fr]">
      <Field label="Code" htmlFor={`d-code-${division?.id ?? "new"}`} error={form.formState.errors.code?.message} required>
        <Input className="font-mono uppercase" {...form.register("code")} />
      </Field>
      <Field label="Name" htmlFor={`d-name-${division?.id ?? "new"}`} error={form.formState.errors.name?.message} required>
        <Input {...form.register("name")} />
      </Field>
      <Field label="Description" htmlFor={`d-desc-${division?.id ?? "new"}`} className="sm:col-span-2">
        <Input {...form.register("description")} />
      </Field>
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button type="button" variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" size="sm" loading={form.formState.isSubmitting}>
          {division ? "Save division" : "Add division"}
        </Button>
      </div>
    </form>
  );
}

export function DivisionsDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const divisions = useDivisionsQuery();
  const canManage = useCan("divisions:manage");
  const { deleteDivision } = useOrgMutations();
  const [editing, setEditing] = React.useState<Division | "new" | null>(null);
  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent title="Divisions" description="Business units that own projects (e.g. Industrial Automation, Power Systems).">
        <div className="space-y-3">
          {canManage && editing === null && (
            <Button variant="secondary" size="sm" onClick={() => setEditing("new")}>
              <Plus /> Add division
            </Button>
          )}
          {editing === "new" && <DivisionForm division={null} onDone={() => setEditing(null)} />}
          <ul className="divide-y rounded-md border" aria-label="Division list">
            {(divisions.data ?? []).map((d) =>
              editing !== "new" && editing?.id === d.id ? (
                <li key={d.id} className="p-2">
                  <DivisionForm division={d} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li key={d.id} className="flex items-center gap-3 px-3 py-2">
                  <MonoText className="w-24 text-neutral-600">{d.code}</MonoText>
                  <span className="min-w-0 flex-1 truncate text-sm">{d.name}</span>
                  {canManage && (
                    <>
                      <Button size="icon-sm" variant="ghost" aria-label={`Edit ${d.name}`} onClick={() => setEditing(d)}>
                        <Pencil />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`Delete ${d.name}`}
                        onClick={() =>
                          deleteDivision.mutate(
                            { id: d.id, row_version: d.row_version },
                            { onSuccess: () => toast.success("Division deleted"), onError: (err) => toast.error(errorMessage(err)) },
                          )
                        }
                      >
                        <Trash2 />
                      </Button>
                    </>
                  )}
                </li>
              ),
            )}
          </ul>
        </div>
      </DrawerContent>
    </Drawer>
  );
}

/* ---------------------------------------------------------------- clone */

const cloneSchema = z
  .object({ name: z.string().trim().min(1, "Enter a name").max(200), client_po_ref: z.string().max(100), start_date: z.date().nullable(), due_date: z.date().nullable(), include_boq: z.boolean() })
  .refine((v) => !v.start_date || !v.due_date || v.due_date >= v.start_date, { path: ["due_date"], message: "Due date is before the start date" });

export function CloneDialog({ project, open, onClose, onCloned }: { project: Project; open: boolean; onClose: () => void; onCloned: (p: Project) => void }) {
  const { cloneProject } = useOrgMutations();
  const form = useForm<z.infer<typeof cloneSchema>>({
    resolver: zodResolver(cloneSchema),
    values: { name: `${project.name} (repeat)`, client_po_ref: "", start_date: null, due_date: null, include_boq: true },
  });
  const submit = form.handleSubmit(async (v) => {
    try {
      const clone = await cloneProject.mutateAsync({
        id: project.id, name: v.name, client_po_ref: v.client_po_ref || null, start_date: toIsoDate(v.start_date), due_date: toIsoDate(v.due_date), include_boq: v.include_boq,
      });
      toast.success(`Created ${clone.code} from ${project.code}`);
      onCloned(clone);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  });
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={`Clone ${project.code}`}
        description="For a repeat order: copies modules and PCB assemblies (with their drawing and KiCad files), optionally the current BOQs. Nothing from procurement, production or QC is copied."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => void submit()} loading={form.formState.isSubmitting}>
              Create copy
            </Button>
          </>
        }
      >
        <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
          <Field label="New project name" htmlFor="c-name" className="sm:col-span-2" error={form.formState.errors.name?.message} required>
            <Input {...form.register("name")} />
          </Field>
          <Field label="Client PO reference" htmlFor="c-po" className="sm:col-span-2">
            <Input className="font-mono" {...form.register("client_po_ref")} />
          </Field>
          <Field label="Start date" htmlFor="c-start">
            <Controller control={form.control} name="start_date" render={({ field }) => <DatePicker value={field.value} onChange={field.onChange} />} />
          </Field>
          <Field label="Due date" htmlFor="c-due" error={form.formState.errors.due_date?.message}>
            <Controller control={form.control} name="due_date" render={({ field }) => <DatePicker value={field.value} onChange={field.onChange} />} />
          </Field>
          <Controller control={form.control} name="include_boq" render={({ field }) => (
            <div className="flex items-center gap-2 sm:col-span-2">
              <Checkbox id="c-boq" checked={field.value} onCheckedChange={(v) => field.onChange(v === true)} />
              <Label htmlFor="c-boq">Copy the current revision of each BOQ (as draft revision A)</Label>
            </div>
          )} />
        </form>
      </DialogContent>
    </Dialog>
  );
}

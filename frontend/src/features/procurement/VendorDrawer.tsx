import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { Button, Drawer, DrawerContent, Field, Input, NumberInput, Textarea, toast } from "@/design/components";
import { Attachments } from "@/features/attachments/Attachments";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";

import { type Vendor, type VendorInput, useProcurementMutations } from "./api";

const GSTIN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

const schema = z.object({
  code: z.string().trim().toUpperCase().regex(/^[A-Z0-9][A-Z0-9_-]{1,31}$/, "2-32 letters, digits, dash or underscore"),
  name: z.string().trim().min(1, "Enter the vendor name").max(200),
  gstin: z
    .string()
    .trim()
    .toUpperCase()
    .refine((v) => v === "" || GSTIN.test(v), "15 characters: state code, PAN, entity, Z, checksum"),
  address: z.string().max(1000),
  city: z.string().max(100),
  state: z.string().max(100),
  payment_terms: z.string().max(100),
  lead_time_days: z.number().int().min(0).max(730).nullable(),
  rating: z.number().min(0).max(5).nullable(),
  notes: z.string().max(5000),
  contacts: z.array(
    z.object({
      name: z.string().trim().min(1, "Name"),
      role: z.string().max(80),
      phone: z.string().max(40),
      email: z.string().max(200),
    }),
  ),
});
type Form = z.infer<typeof schema>;

const blank = (s: string) => (s.trim() === "" ? null : s.trim());

export function VendorDrawer({ open, vendor, onClose }: { open: boolean; vendor: Vendor | null; onClose: () => void }) {
  const canManage = useCan("vendors:manage");
  const { createVendor, updateVendor } = useProcurementMutations();
  const [error, setError] = React.useState<string | null>(null);
  const form = useForm<Form>({
    resolver: zodResolver(schema),
    values: {
      code: vendor?.code ?? "",
      name: vendor?.name ?? "",
      gstin: vendor?.gstin ?? "",
      address: vendor?.address ?? "",
      city: vendor?.city ?? "",
      state: vendor?.state ?? "",
      payment_terms: vendor?.payment_terms ?? "",
      lead_time_days: vendor?.lead_time_days ?? null,
      rating: vendor?.rating === null || vendor?.rating === undefined ? null : Number(vendor.rating),
      notes: vendor?.notes ?? "",
      contacts: (vendor?.contacts ?? []).map((c) => ({ name: c.name, role: c.role ?? "", phone: c.phone ?? "", email: c.email ?? "" })),
    },
  });
  const contacts = useFieldArray({ control: form.control, name: "contacts" });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (v) => {
    setError(null);
    const body: VendorInput = {
      code: v.code,
      name: v.name,
      gstin: blank(v.gstin),
      address: blank(v.address),
      city: blank(v.city),
      state: blank(v.state),
      payment_terms: blank(v.payment_terms),
      lead_time_days: v.lead_time_days,
      rating: v.rating === null ? null : v.rating.toFixed(1),
      notes: blank(v.notes),
      contacts: v.contacts.map((c) => ({ name: c.name, role: blank(c.role), phone: blank(c.phone), email: blank(c.email) })),
    };
    try {
      const saved = vendor ? await updateVendor.mutateAsync({ id: vendor.id, row_version: vendor.row_version, ...body }) : await createVendor.mutateAsync(body);
      toast.success(vendor ? "Vendor saved" : `Vendor ${saved.name} added`);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the vendor");
    }
  });

  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        width="620px"
        title={vendor ? `${vendor.name}` : "New vendor"}
        description={vendor ? `Vendor ${vendor.code}` : "Approved supplier details used on purchase orders."}
        footer={
          canManage && (
            <>
              <Button variant="secondary" onClick={onClose}>Cancel</Button>
              <Button onClick={() => void submit()} loading={form.formState.isSubmitting}>{vendor ? "Save vendor" : "Add vendor"}</Button>
            </>
          )
        }
      >
        <fieldset disabled={!canManage} className="grid gap-4">
          {error && <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">{error}</p>}
          <div className="grid gap-4 sm:grid-cols-[10rem_minmax(0,1fr)]">
            <Field label="Code" htmlFor="v-code" required error={errors.code?.message}>
              <Input className="font-mono uppercase" {...form.register("code")} />
            </Field>
            <Field label="Name" htmlFor="v-name" required error={errors.name?.message}>
              <Input {...form.register("name")} />
            </Field>
          </div>
          <Field label="GSTIN" htmlFor="v-gstin" error={errors.gstin?.message} hint="Checked for the 15-character format">
            <Input className="font-mono uppercase" {...form.register("gstin")} />
          </Field>
          <Field label="Address" htmlFor="v-address">
            <Textarea rows={2} {...form.register("address")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="City" htmlFor="v-city"><Input {...form.register("city")} /></Field>
            <Field label="State" htmlFor="v-state"><Input {...form.register("state")} /></Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Payment terms" htmlFor="v-terms"><Input placeholder="e.g. 30 days" {...form.register("payment_terms")} /></Field>
            <Field label="Lead time" htmlFor="v-lead" error={errors.lead_time_days?.message}>
              <Controller control={form.control} name="lead_time_days" render={({ field }) => <NumberInput value={field.value} onValueChange={field.onChange} unit="days" min={0} max={730} />} />
            </Field>
            <Field label="Rating" htmlFor="v-rating" hint="0 to 5">
              <Controller control={form.control} name="rating" render={({ field }) => <NumberInput value={field.value} onValueChange={field.onChange} min={0} max={5} step={0.5} precision={1} />} />
            </Field>
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-800">Contacts</h3>
              <Button type="button" size="sm" variant="ghost" onClick={() => contacts.append({ name: "", role: "", phone: "", email: "" })}>
                <Plus /> Add contact
              </Button>
            </div>
            {contacts.fields.length === 0 && <p className="text-sm text-neutral-500">No contacts yet.</p>}
            <ul className="space-y-2">
              {contacts.fields.map((c, i) => (
                <li key={c.id} className="grid grid-cols-[1fr_0.8fr_0.9fr_1.2fr_auto] items-start gap-2">
                  <Input aria-label={`Contact ${i + 1} name`} placeholder="Name" aria-invalid={!!errors.contacts?.[i]?.name} {...form.register(`contacts.${i}.name`)} />
                  <Input aria-label={`Contact ${i + 1} role`} placeholder="Role" {...form.register(`contacts.${i}.role`)} />
                  <Input aria-label={`Contact ${i + 1} phone`} placeholder="Phone" {...form.register(`contacts.${i}.phone`)} />
                  <Input aria-label={`Contact ${i + 1} email`} placeholder="Email" {...form.register(`contacts.${i}.email`)} />
                  <Button type="button" variant="ghost" size="icon" aria-label={`Remove contact ${i + 1}`} onClick={() => contacts.remove(i)}>
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
          <Field label="Notes" htmlFor="v-notes"><Textarea rows={2} {...form.register("notes")} /></Field>
        </fieldset>
        {vendor && (
          <div className="mt-6">
            <Attachments refType="vendor" refId={vendor.id} title="Vendor documents" />
          </div>
        )}
      </DrawerContent>
    </Drawer>
  );
}

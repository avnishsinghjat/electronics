import { zodResolver } from "@hookform/resolvers/zod";
import { Save } from "lucide-react";
import * as React from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Button, Card, CardContent, CardHeader, Field, FileDropzone, Input, MonoText, Skeleton, Textarea, toast } from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { useBranding } from "@/features/auth/AuthLayout";
import { ApiError } from "@/lib/api";

import { type Company, useCompany, useNumbering, useSaveCompany, useSavePrefix, useUploadLogo } from "./api";

const companySchema = z.object({
  company_name: z.string().trim().min(1, "Enter the company name").max(200),
  address: z.string().max(500),
  serial_prefix: z.string().trim().regex(/^[A-Z0-9]{1,8}$/, "1-8 capital letters or digits"),
  gstin: z.union([z.literal(""), z.string().regex(/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/, "Not a valid 15-character GSTIN")]),
});
type CompanyForm = z.infer<typeof companySchema>;

function CompanyCard({ company, canEdit }: { company: Company; canEdit: boolean }) {
  const save = useSaveCompany();
  const form = useForm<CompanyForm>({
    resolver: zodResolver(companySchema),
    values: { company_name: company.company_name, address: company.address ?? "", gstin: company.gstin ?? "", serial_prefix: company.serial_prefix },
  });
  const prefix = useWatch({ control: form.control, name: "serial_prefix" });
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      await save.mutateAsync({ row_version: company.row_version, company_name: v.company_name, address: v.address || null, gstin: v.gstin || null, serial_prefix: v.serial_prefix });
      toast.success("Company details saved");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not save");
    }
  });
  return (
    <Card>
      <CardHeader title="Company" description="Shown on the sign-in page, purchase orders and reports." />
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="grid gap-4 md:grid-cols-2">
          <Field label="Company name" htmlFor="company_name" error={form.formState.errors.company_name?.message} required>
            <Input disabled={!canEdit} {...form.register("company_name")} />
          </Field>
          <Field label="GSTIN" htmlFor="gstin" hint="15 characters, e.g. 27AABCS1234F1Z5" error={form.formState.errors.gstin?.message}>
            <Input disabled={!canEdit} className="font-mono uppercase" {...form.register("gstin", { setValueAs: (v: string) => v.toUpperCase().trim() })} />
          </Field>
          <Field label="Serial number prefix" htmlFor="serial_prefix" hint={`Serials look like ${prefix || "SN"}-CPU1-${new Date().getFullYear()}-00001`} error={form.formState.errors.serial_prefix?.message}>
            <Input disabled={!canEdit} className="font-mono uppercase" {...form.register("serial_prefix", { setValueAs: (v: string) => v.toUpperCase().trim() })} />
          </Field>
          <Field label="Address" htmlFor="address" className="md:col-span-2" error={form.formState.errors.address?.message}>
            <Textarea disabled={!canEdit} rows={3} {...form.register("address")} />
          </Field>
          {canEdit && (
            <div className="md:col-span-2">
              <Button type="submit" loading={save.isPending} disabled={!form.formState.isDirty}>
                {!save.isPending && <Save />} Save company details
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function LogoCard({ canEdit }: { canEdit: boolean }) {
  const branding = useBranding();
  const upload = useUploadLogo();
  const [version, setVersion] = React.useState(0);
  return (
    <Card>
      <CardHeader title="Logo" description="PNG, JPEG or WebP up to 2 MB." />
      <CardContent className="flex flex-col gap-4 md:flex-row md:items-start">
        <div className="flex h-24 w-48 shrink-0 items-center justify-center rounded-md border bg-neutral-25">
          {branding.data?.logo_url ? (
            <img src={`${branding.data.logo_url}?v=${version}`} alt="Current company logo" className="max-h-20 max-w-44 object-contain" />
          ) : (
            <span className="text-xs text-neutral-500">No logo yet</span>
          )}
        </div>
        {canEdit && (
          <div className="flex-1">
            <FileDropzone
              multiple={false}
              accept={["image/png", "image/jpeg", "image/webp"]}
              maxSizeBytes={2 * 1024 * 1024}
              disabled={upload.isPending}
              label="Drop a new logo or browse"
              onFiles={(files) => {
                const f = files[0];
                if (!f) return;
                upload.mutate(f, {
                  onSuccess: () => {
                    setVersion((v) => v + 1);
                    toast.success("Logo updated");
                  },
                  onError: (err) => toast.error(err instanceof ApiError ? err.message : "Upload failed"),
                });
              }}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function NumberingCard({ canEdit }: { canEdit: boolean }) {
  const numbering = useNumbering();
  const save = useSavePrefix();
  const [draft, setDraft] = React.useState<Record<string, string>>({});
  return (
    <Card>
      <CardHeader title="Document numbering" description="Prefixes for document numbers. Numbers are gap-free and restart each year; existing numbers never change." />
      <CardContent className="p-0">
        {numbering.isPending ? (
          <div className="space-y-2 p-5">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>
        ) : numbering.isError ? (
          <p role="alert" className="p-5 text-sm text-status-red-fg">{numbering.error.message}</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-xs font-semibold text-neutral-600">
              <tr>
                <th scope="col" className="px-5 py-2">Document</th>
                <th scope="col" className="px-3 py-2">Prefix</th>
                <th scope="col" className="px-3 py-2">Next number looks like</th>
                {canEdit && <th scope="col" className="px-5 py-2 text-right"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody>
              {numbering.data.map((n) => {
                const value = draft[n.doc_type] ?? n.prefix;
                const dirty = value !== n.prefix;
                return (
                  <tr key={n.doc_type} className="border-t">
                    <td className="px-5 py-2 text-neutral-800">{n.description}</td>
                    <td className="px-3 py-1.5">
                      {canEdit ? (
                        <Input
                          aria-label={`Prefix for ${n.description}`}
                          className="h-8 w-28 font-mono uppercase"
                          maxLength={16}
                          value={value}
                          onChange={(e) => setDraft((d) => ({ ...d, [n.doc_type]: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") }))}
                        />
                      ) : (
                        <MonoText>{n.prefix}</MonoText>
                      )}
                    </td>
                    <td className="px-3 py-2"><MonoText>{n.example.replace(n.prefix, value || n.prefix)}</MonoText></td>
                    {canEdit && (
                      <td className="px-5 py-1.5 text-right">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={!dirty || !value}
                          loading={save.isPending && save.variables?.doc_type === n.doc_type}
                          onClick={() =>
                            save.mutate(
                              { doc_type: n.doc_type, prefix: value },
                              {
                                onSuccess: () => {
                                  toast.success(`${n.description} prefix set to ${value}`);
                                  setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== n.doc_type)));
                                },
                                onError: (err) => toast.error(err instanceof ApiError ? err.message : "Could not save"),
                              },
                            )
                          }
                        >
                          Save
                        </Button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

export default function GeneralSettingsPage() {
  const canEdit = useCan("settings:manage");
  const company = useCompany();
  return (
    <div className="space-y-6">
      {company.isPending ? <Skeleton className="h-48" /> : company.isError ? <p role="alert" className="text-sm text-status-red-fg">{company.error.message}</p> : <CompanyCard company={company.data} canEdit={canEdit} />}
      <LogoCard canEdit={canEdit} />
      <NumberingCard canEdit={canEdit} />
    </div>
  );
}

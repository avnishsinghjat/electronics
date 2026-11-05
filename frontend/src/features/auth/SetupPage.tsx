import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FolderCheck, HardDriveDownload, XCircle } from "lucide-react";
import * as React from "react";
import { useForm } from "react-hook-form";
import { Navigate, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button, Field, FileDropzone, Input, MonoText, Skeleton, Stepper, type Step, toast } from "@/design/components";
import { formatBytes } from "@/features/system/format";
import { ApiError, apiGet, apiPost } from "@/lib/api";

import { useAuth } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { passwordSchema } from "./PasswordFields";
import type { SetupStatus, TokenResponse } from "./types";

type StepId = "check" | "company" | "numbering" | "logo";
const ORDER: StepId[] = ["check", "company", "numbering", "logo"];
const LABELS: Record<StepId, string> = { check: "Data directory", company: "Company and admin", numbering: "Document numbers", logo: "Logo" };

const companySchema = z
  .object({
    company_name: z.string().trim().min(1, "Enter the company name").max(200),
    username: z.string().trim().regex(/^[A-Za-z0-9._-]{3,64}$/, "3-64 letters, digits, dot, dash or underscore"),
    full_name: z.string().trim().min(1, "Enter the administrator's name"),
    password: z.string(),
    confirm: z.string(),
  })
  .superRefine((v, ctx) => {
    const res = passwordSchema(v.username).safeParse(v.password);
    if (!res.success) ctx.addIssue({ code: "custom", path: ["password"], message: res.error.issues[0]?.message ?? "Weak password" });
    if (v.password !== v.confirm) ctx.addIssue({ code: "custom", path: ["confirm"], message: "Passwords do not match" });
  });
type CompanyValues = z.infer<typeof companySchema>;

export default function SetupPage() {
  const { status, acceptSession } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = React.useState<StepId>("check");
  const [company, setCompany] = React.useState<CompanyValues | null>(null);
  const [prefixes, setPrefixes] = React.useState<Record<string, string>>({});
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const setup = useQuery({ queryKey: ["setup-status"], queryFn: () => apiGet<SetupStatus>("/setup/status"), enabled: step !== "logo" });
  const form = useForm<CompanyValues>({ resolver: zodResolver(companySchema), defaultValues: { company_name: "", username: "admin", full_name: "", password: "", confirm: "" } });

  if (status === "authenticated" && step !== "logo") return <Navigate to="/" replace />;
  if (status === "anonymous") return <Navigate to="/login" replace />;

  const steps: Step[] = ORDER.map((id, i) => ({
    id,
    label: LABELS[id],
    state: i < ORDER.indexOf(step) ? "complete" : id === step ? "current" : "upcoming",
  }));

  const submit = async () => {
    if (!company) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const changed = Object.fromEntries(
        Object.entries(prefixes).filter(([type, prefix]) => setup.data?.numbering.find((n) => n.doc_type === type)?.prefix !== prefix),
      );
      const token = await apiPost<TokenResponse>(
        "/setup",
        { company_name: company.company_name, admin: { username: company.username, full_name: company.full_name, password: company.password }, prefixes: changed },
        { anonymous: true },
      );
      acceptSession(token);
      setStep("logo");
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Setup failed");
    } finally {
      setSubmitting(false);
    }
  };

  const uploadLogo = async (files: File[]) => {
    const file = files[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    setUploading(true);
    try {
      await apiPost("/settings/logo", body);
      toast.success("Logo uploaded");
      navigate("/", { replace: true });
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <AuthLayout wide title="Set up FabTrack" subtitle="One-time setup for this server. Takes about two minutes.">
      <Stepper steps={steps} className="mb-6" />

      {step === "check" && (
        <div className="space-y-4">
          {setup.isPending && <Skeleton className="h-20" />}
          {setup.isError && <p role="alert" className="text-sm text-status-red-fg">Could not reach the server: {setup.error.message}</p>}
          {setup.data && (
            <div className="rounded-md border bg-neutral-25 p-4">
              <div className="flex items-start gap-3">
                {setup.data.data_dir.ok ? (
                  <CheckCircle2 className="mt-0.5 size-5 text-status-green-dot" aria-hidden="true" />
                ) : (
                  <XCircle className="mt-0.5 size-5 text-status-red-dot" aria-hidden="true" />
                )}
                <div className="min-w-0 text-sm">
                  <p className="font-medium text-neutral-900">{setup.data.data_dir.ok ? "Data directory is ready" : "Data directory needs attention"}</p>
                  <p className="mt-1 break-all text-neutral-600">
                    <FolderCheck className="mr-1 inline size-3.5" aria-hidden="true" />
                    <MonoText>{setup.data.data_dir.path}</MonoText>
                  </p>
                  <p className="mt-1 text-neutral-600">
                    <HardDriveDownload className="mr-1 inline size-3.5" aria-hidden="true" />
                    {formatBytes(setup.data.data_dir.free_bytes)} free · {setup.data.data_dir.writable ? "writable" : "not writable"}
                  </p>
                  {setup.data.data_dir.detail && <p className="mt-1 text-status-red-fg">{setup.data.data_dir.detail}</p>}
                  <p className="mt-2 text-xs text-neutral-500">Photos, documents and KiCad projects are stored here. Back it up with the database.</p>
                </div>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => void setup.refetch()} loading={setup.isFetching}>
              Check again
            </Button>
            <Button onClick={() => setStep("company")} disabled={!setup.data?.data_dir.ok}>
              Continue <ArrowRight />
            </Button>
          </div>
        </div>
      )}

      {step === "company" && (
        <form
          noValidate
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={form.handleSubmit((v) => {
            setCompany(v);
            setPrefixes(Object.fromEntries((setup.data?.numbering ?? []).map((n) => [n.doc_type, n.prefix])));
            setStep("numbering");
          })}
        >
          <Field label="Company name" htmlFor="company_name" className="sm:col-span-2" hint="Printed on POs, reports and the sign-in page" error={form.formState.errors.company_name?.message} required>
            <Input autoFocus {...form.register("company_name")} />
          </Field>
          <Field label="Administrator username" htmlFor="username" error={form.formState.errors.username?.message} required>
            <Input autoComplete="username" autoCapitalize="none" {...form.register("username")} />
          </Field>
          <Field label="Administrator full name" htmlFor="full_name" error={form.formState.errors.full_name?.message} required>
            <Input autoComplete="name" {...form.register("full_name")} />
          </Field>
          <Field label="Password" htmlFor="password" hint="10+ characters, letters with digits or symbols" error={form.formState.errors.password?.message} required>
            <Input type="password" autoComplete="new-password" {...form.register("password")} />
          </Field>
          <Field label="Confirm password" htmlFor="confirm" error={form.formState.errors.confirm?.message} required>
            <Input type="password" autoComplete="new-password" {...form.register("confirm")} />
          </Field>
          <div className="flex justify-between gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={() => setStep("check")}>
              Back
            </Button>
            <Button type="submit">
              Continue <ArrowRight />
            </Button>
          </div>
        </form>
      )}

      {step === "numbering" && setup.data && (
        <div className="space-y-4">
          <p className="text-sm text-neutral-600">Document numbers look like <MonoText>PO-2026-0001</MonoText> and restart every year. Change a prefix if your company already uses one.</p>
          {submitError && (
            <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">
              {submitError}
            </p>
          )}
          <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
            {setup.data.numbering.map((n) => (
              <Field key={n.doc_type} label={n.description} htmlFor={`prefix-${n.doc_type}`} hint={`Example: ${(prefixes[n.doc_type] || n.prefix).toUpperCase()}-${new Date().getFullYear()}-0001`}>
                <Input
                  className="font-mono uppercase"
                  maxLength={16}
                  value={prefixes[n.doc_type] ?? n.prefix}
                  onChange={(e) => setPrefixes((p) => ({ ...p, [n.doc_type]: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "") }))}
                />
              </Field>
            ))}
          </div>
          <div className="flex justify-between gap-2">
            <Button variant="ghost" onClick={() => setStep("company")}>
              Back
            </Button>
            <Button onClick={() => void submit()} loading={submitting} disabled={Object.values(prefixes).some((p) => !p)}>
              Create company and administrator
            </Button>
          </div>
        </div>
      )}

      {step === "logo" && (
        <div className="space-y-4">
          <p className="text-sm text-neutral-600">Setup is complete and you are signed in. Optionally add your company logo; it appears on the sign-in page and on documents.</p>
          <FileDropzone onFiles={(f) => void uploadLogo(f)} accept={["image/png", "image/jpeg", "image/webp"]} maxSizeBytes={2 * 1024 * 1024} multiple={false} disabled={uploading} label="Drop your logo here or browse" hint="PNG, JPEG or WebP, up to 2 MB" />
          <div className="flex justify-end">
            <Button variant="secondary" onClick={() => navigate("/", { replace: true })}>
              Skip for now
            </Button>
          </div>
        </div>
      )}
    </AuthLayout>
  );
}

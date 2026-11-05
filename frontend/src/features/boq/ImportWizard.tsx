import type { ColumnDef } from "@tanstack/react-table";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Info, Loader2, XCircle } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Checkbox,
  DataTable,
  Dialog,
  DialogContent,
  Field,
  FileDropzone,
  Input,
  Label,
  MonoText,
  NumberInput,
  Select,
  StatCard,
  StatusPill,
  Stepper,
  type Step,
  toast,
} from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError, apiBlob } from "@/lib/api";
import { cn } from "@/lib/utils";

import { type ImportSession, type Issue, templateMapping, useImportFields, useImportMutations, useImportSession, useTemplates } from "./api";

const NONE = "__none";
const STEP_ORDER = ["upload", "mapping", "review", "done"] as const;
type WizardStep = (typeof STEP_ORDER)[number];

const SEVERITY: Record<Issue["severity"], { tone: "red" | "amber" | "blue"; icon: typeof XCircle; label: string }> = {
  error: { tone: "red", icon: XCircle, label: "Error" },
  warning: { tone: "amber", icon: AlertTriangle, label: "Warning" },
  info: { tone: "blue", icon: Info, label: "Info" },
};

const issueColumns: ColumnDef<Issue, unknown>[] = [
  { accessorKey: "row", header: "Row", size: 70, meta: { mono: true, align: "right", exportType: "number" } },
  {
    accessorKey: "severity",
    header: "Severity",
    size: 110,
    cell: ({ getValue }) => {
      const s = SEVERITY[getValue() as Issue["severity"]];
      return <StatusPill tone={s.tone}>{s.label}</StatusPill>;
    },
  },
  { accessorKey: "field", header: "Field", size: 100 },
  { accessorKey: "message", header: "Problem", size: 400 },
  { accessorKey: "code", header: "Code", size: 160, meta: { mono: true } },
];

function MappingStep({ session, client, onValidate, busy }: {
  session: ImportSession;
  client: string | null;
  onValidate: (args: { header_row: number; mapping: Record<string, number>; decimal_comma: boolean; save_template_name: string | null }) => void;
  busy: boolean;
}) {
  const fields = useImportFields();
  const templates = useTemplates();
  const [headerRow, setHeaderRow] = React.useState(session.header_row ?? 0);
  const [mapping, setMapping] = React.useState<Record<string, number>>(session.mapping ?? {});
  const [decimalComma, setDecimalComma] = React.useState(session.delimiter === ";");
  const [saveName, setSaveName] = React.useState("");
  const [saveOn, setSaveOn] = React.useState(false);
  const headers = session.preview_rows[headerRow] ?? [];
  const columnOptions = [{ value: NONE, label: "— not in file —" }, ...headers.map((h, i) => ({ value: String(i), label: h ? `${String.fromCharCode(65 + (i % 26))}: ${h}` : `Column ${i + 1}` }))];

  const apply = async (templateId: string) => {
    try {
      setMapping(await templateMapping(session.id, templateId));
      toast.success("Template applied");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not apply the template");
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
        <Badge tone="outline">{session.file_name}</Badge>
        {session.encoding && <Badge tone="outline">Encoding {session.encoding}</Badge>}
        {session.delimiter && <Badge tone="outline">Delimiter “{session.delimiter === "\t" ? "tab" : session.delimiter}”</Badge>}
        {session.sheet && <Badge tone="outline">Sheet {session.sheet}</Badge>}
        <Badge tone="outline">{session.total_rows} rows</Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Field label="Header row" htmlFor="imp-header" hint="FabTrack picked the row that looks most like column headings">
          <Select
            value={String(headerRow)}
            onValueChange={(v) => setHeaderRow(Number(v))}
            options={session.preview_rows.slice(0, 20).map((r, i) => ({ value: String(i), label: `Row ${i + 1}: ${r.filter(Boolean).slice(0, 4).join(" | ").slice(0, 60) || "(empty)"}` }))}
          />
        </Field>
        <Field label="Saved mapping" htmlFor="imp-template" hint={session.suggested_template_id ? "A saved mapping matches this file and was applied" : "Apply a mapping saved for an earlier file"}>
          <Select
            value={undefined}
            placeholder={templates.data?.length ? "Apply a saved mapping…" : "No saved mappings yet"}
            disabled={!templates.data?.length}
            onValueChange={(id) => void apply(id)}
            options={(templates.data ?? []).map((t) => ({ value: t.id, label: t.client_name ? `${t.name} (${t.client_name})` : t.name }))}
          />
        </Field>
      </div>

      <div className="rounded-lg border">
        <table className="w-full text-sm" aria-label="Column mapping">
          <thead className="bg-neutral-50 text-left text-xs font-semibold text-neutral-600">
            <tr>
              <th scope="col" className="px-3 py-2">FabTrack field</th>
              <th scope="col" className="px-3 py-2">Column in your file</th>
              <th scope="col" className="px-3 py-2">First values</th>
            </tr>
          </thead>
          <tbody>
            {(fields.data ?? []).map((f) => {
              const col = mapping[f.field];
              const samples = col === undefined ? [] : session.preview_rows.slice(headerRow + 1, headerRow + 4).map((r) => r[col] ?? "");
              return (
                <tr key={f.field} className="border-t">
                  <td className="px-3 py-1.5 font-medium text-neutral-800">
                    {f.label}
                    {(f.field === "mpn" || f.field === "qty") && <span className="ml-1 text-xs font-normal text-neutral-500">(needed)</span>}
                  </td>
                  <td className="w-72 px-3 py-1.5">
                    <Select
                      aria-label={`Column for ${f.label}`}
                      value={col === undefined ? NONE : String(col)}
                      onValueChange={(v) =>
                        setMapping((m) => {
                          const next = Object.fromEntries(Object.entries(m).filter(([k]) => k !== f.field));
                          return v === NONE ? next : { ...next, [f.field]: Number(v) };
                        })
                      }
                      options={columnOptions}
                    />
                  </td>
                  <td className="truncate px-3 py-1.5 font-mono text-xs text-neutral-600">{samples.filter(Boolean).join(" · ") || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-center gap-2">
          <Checkbox id="imp-comma" checked={decimalComma} onCheckedChange={(v) => setDecimalComma(v === true)} />
          <Label htmlFor="imp-comma">Numbers use a decimal comma (1,5)</Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox id="imp-save" checked={saveOn} onCheckedChange={(v) => setSaveOn(v === true)} />
          <Label htmlFor="imp-save">Save this mapping{client ? ` for ${client}` : ""}</Label>
        </div>
        {saveOn && <Input aria-label="Mapping name" placeholder="Mapping name" className="h-8 w-56" value={saveName} onChange={(e) => setSaveName(e.target.value)} />}
      </div>

      <div className="flex justify-end">
        <Button
          onClick={() => onValidate({ header_row: headerRow, mapping, decimal_comma: decimalComma, save_template_name: saveOn && saveName.trim() ? saveName.trim() : null })}
          loading={busy}
          disabled={mapping.mpn === undefined && mapping.description === undefined}
        >
          Validate file
        </Button>
      </div>
    </div>
  );
}

function ReviewStep({ session, onCommit, onRemap, committing }: {
  session: ImportSession;
  onCommit: (opts: { release: boolean; build_qty: number | null }) => void;
  onRemap: () => void;
  committing: boolean;
}) {
  const canRelease = useCan("boq:release");
  const [release, setRelease] = React.useState(false);
  const [buildQty, setBuildQty] = React.useState<number | null>(null);
  const stats = session.result?.stats ?? {};
  const errors = stats.errors ?? 0;

  const download = async () => {
    try {
      const blob = await apiBlob(`/boq-imports/${session.id}/errors.csv`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${session.file_name.replace(/\.[^.]+$/, "")}-import-report.csv`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      toast.error("Could not download the report");
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatCard label="Rows read" value={stats.source_rows ?? 0} />
        <StatCard label="BOQ lines" value={stats.lines ?? 0} hint="after merging same MPN" />
        <StatCard label="Errors" value={errors} />
        <StatCard label="Warnings" value={stats.warnings ?? 0} hint={`${stats.unknown_parts ?? 0} new parts`} />
      </div>
      <div
        role="status"
        className={cn(
          "flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
          errors ? "border-status-red-border bg-status-red-bg text-status-red-fg" : "border-status-green-border bg-status-green-bg text-status-green-fg",
        )}
      >
        {errors ? <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
        {errors
          ? `${errors} error${errors === 1 ? "" : "s"} must be fixed in the file (or the mapping) before it can be committed. Nothing has been saved.`
          : "No errors. Committing creates a new BOQ revision; warnings are for your information."}
      </div>
      <DataTable
        id="boq-import-issues"
        data={session.result?.issues ?? []}
        columns={issueColumns}
        getRowId={(i) => `${i.row}-${i.code}-${i.field}`}
        maxHeight={300}
        exportFileName="boq-import-issues"
        toolbar={
          <Button size="sm" variant="secondary" onClick={() => void download()}>
            <Download /> Error report CSV
          </Button>
        }
        emptyState={<p className="px-3 py-6 text-center text-sm text-neutral-500">No issues found.</p>}
      />
      <div className="flex flex-wrap items-end justify-between gap-4 border-t pt-4">
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Build quantity" htmlFor="imp-build" hint="Leave empty to keep the current value">
            <NumberInput value={buildQty} onValueChange={setBuildQty} unit="units" min={0} className="w-48" />
          </Field>
          {canRelease && (
            <div className="flex items-center gap-2 pb-2">
              <Checkbox id="imp-release" checked={release} onCheckedChange={(v) => setRelease(v === true)} />
              <Label htmlFor="imp-release">Release the revision immediately</Label>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onRemap}>Change mapping</Button>
          <Button onClick={() => onCommit({ release, build_qty: buildQty })} disabled={errors > 0} loading={committing}>
            Commit as new revision
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ImportWizard({ boqId, client, open, onClose, onCommitted }: {
  boqId: string;
  client: string | null;
  open: boolean;
  onClose: () => void;
  onCommitted: (revisionId: string) => void;
}) {
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [remap, setRemap] = React.useState(false);
  const session = useImportSession(sessionId);
  const { upload, setMapping, commit } = useImportMutations();
  const s = session.data;

  const step: WizardStep = !s ? "upload" : s.status === "committed" ? "done" : s.status === "validated" && !remap ? "review" : "mapping";
  const busy = !!s && ["uploaded", "parsing", "validating"].includes(s.status);
  const steps: Step[] = [
    { id: "upload", label: "Upload" },
    { id: "mapping", label: "Map columns" },
    { id: "review", label: "Check" },
    { id: "done", label: "Commit" },
  ].map((x, i) => ({ ...x, state: i < STEP_ORDER.indexOf(step) ? "complete" : x.id === step ? "current" : "upcoming" }));

  const reset = () => {
    setSessionId(null);
    setRemap(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose(); } }}>
      <DialogContent size="xl" title="Import BOQ" description="CSV, Excel (XLSX) or a KiCad BOM export. Nothing is saved until you commit.">
        <Stepper steps={steps} className="mb-5" />
        {step === "upload" && (
          <FileDropzone
            multiple={false}
            accept={[".csv", ".txt", ".tsv", ".xlsx", ".xlsm"]}
            disabled={upload.isPending}
            label={upload.isPending ? "Uploading…" : "Drop the BOQ file here or browse"}
            hint="UTF-8, UTF-8 with BOM or Windows-1252 · comma, semicolon or tab separated · title rows above the header are fine"
            onFiles={(files) => {
              const file = files[0];
              if (!file) return;
              upload.mutate({ boqId, file }, { onSuccess: (r) => setSessionId(r.id), onError: (err) => toast.error(err instanceof ApiError ? err.message : "Upload failed") });
            }}
          />
        )}
        {busy && (
          <p role="status" className="flex items-center gap-2 py-8 text-sm text-neutral-600">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" /> {s?.status === "validating" ? "Checking every row…" : "Reading the file…"}
          </p>
        )}
        {s?.status === "failed" && (
          <div role="alert" className="space-y-3">
            <p className="flex items-center gap-2 text-sm text-status-red-fg"><FileSpreadsheet className="size-4" aria-hidden="true" /> {s.error}</p>
            <Button variant="secondary" onClick={reset}>Choose another file</Button>
          </div>
        )}
        {step === "mapping" && s && !busy && s.status !== "failed" && (
          <MappingStep
            session={s}
            client={client}
            busy={setMapping.isPending}
            onValidate={(args) =>
              setMapping.mutate(
                { id: s.id, row_version: s.row_version, template_client: client, ...args },
                { onSuccess: () => setRemap(false), onError: (err) => toast.error(err instanceof ApiError ? err.message : "Could not validate") },
              )
            }
          />
        )}
        {step === "review" && s && (
          <ReviewStep
            session={s}
            committing={commit.isPending}
            onRemap={() => setRemap(true)}
            onCommit={(opts) =>
              commit.mutate(
                { id: s.id, row_version: s.row_version, ...opts },
                {
                  onSuccess: (rev) => {
                    toast.success(`Revision ${rev.revision} created with ${rev.line_count} lines`);
                    reset();
                    onCommitted(rev.id);
                  },
                  onError: (err) => toast.error(err instanceof ApiError ? err.message : "Commit failed"),
                },
              )
            }
          />
        )}
        {step === "done" && <p className="text-sm text-neutral-600">This file has already been committed.</p>}
        {s && step !== "upload" && <p className="mt-4 text-xs text-neutral-500">File <MonoText>{s.file_name}</MonoText></p>}
      </DialogContent>
    </Dialog>
  );
}

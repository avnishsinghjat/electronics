import type { ColumnDef } from "@tanstack/react-table";
import { Boxes, FileWarning, Inbox, PackageCheck, Plus, Trash2 } from "lucide-react";
import * as React from "react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  Checkbox,
  Combobox,
  type ComboboxOption,
  DataTable,
  DatePicker,
  Dialog,
  DialogContent,
  DialogTrigger,
  Drawer,
  DrawerContent,
  DrawerTrigger,
  EmptyState,
  Field,
  FileDropzone,
  Input,
  Label,
  MonoText,
  NumberInput,
  PageHeader,
  PhotoGrid,
  ProgressBar,
  Select,
  Skeleton,
  StatCard,
  StatusPill,
  Stepper,
  Switch,
  TONE_MEANING,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  Timeline,
  Tooltip,
  toast,
} from "@/design/components";
import type { StatusTone } from "@/design/tokens";

import { type DemoPart, demoParts, demoPhotoSrc } from "./fixtures";

const SECTIONS = [
  ["buttons", "Buttons"],
  ["forms", "Form controls"],
  ["status", "Badges and status"],
  ["cards", "Cards and KPIs"],
  ["navigation", "Tabs, stepper, timeline"],
  ["overlays", "Dialog, drawer, toast, tooltip"],
  ["feedback", "Empty, skeleton, progress"],
  ["files", "Files and photos"],
  ["table", "Data table (10,000 rows)"],
] as const;

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20">
      <Card>
        <CardHeader title={<span id={`${id}-title`}>{title}</span>} />
        <CardContent className="space-y-5">{children}</CardContent>
      </Card>
    </section>
  );
}

function Demo({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

const MPNS: ComboboxOption[] = [
  { value: "GRM188R71H104KA93D", label: "GRM188R71H104KA93D", description: "Murata · Cap MLCC 100nF 50V X7R 0603" },
  { value: "RC0603FR-0710KL", label: "RC0603FR-0710KL", description: "Yageo · Res 10k 1% 0603" },
  { value: "STM32F407VGT6", label: "STM32F407VGT6", description: "STMicroelectronics · MCU LQFP-100" },
  { value: "TPS54331DR", label: "TPS54331DR", description: "Texas Instruments · Buck 3A SOIC-8" },
  { value: "BSS138", label: "BSS138", description: "onsemi · N-MOSFET SOT-23" },
];

async function searchMpns(query: string): Promise<ComboboxOption[]> {
  const q = query.trim().toLowerCase();
  return MPNS.filter((o) => !q || o.label.toLowerCase().includes(q) || o.description?.toLowerCase().includes(q));
}

const STATUS_TONE: Record<DemoPart["status"], StatusTone> = {
  "Not ordered": "grey",
  Ordered: "blue",
  "Partially received": "amber",
  Received: "green",
  Issued: "green",
};

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2 });

const PART_COLUMNS: ColumnDef<DemoPart, unknown>[] = [
  { accessorKey: "mpn", header: "MPN", size: 190, meta: { mono: true, label: "MPN" } },
  { accessorKey: "manufacturer", header: "Manufacturer", size: 170 },
  { accessorKey: "description", header: "Description", size: 240 },
  { accessorKey: "category", header: "Category", size: 120 },
  {
    accessorKey: "qty",
    header: "Qty",
    size: 100,
    meta: { mono: true, align: "right", exportType: "number", label: "Qty" },
    cell: ({ getValue }) => (getValue() as number).toLocaleString("en-IN"),
  },
  {
    accessorKey: "unitPrice",
    header: "Unit price",
    size: 120,
    meta: { mono: true, align: "right", exportType: "number", label: "Unit price (INR)" },
    cell: ({ getValue }) => inr.format(getValue() as number),
  },
  {
    accessorKey: "status",
    header: "Status",
    size: 160,
    cell: ({ getValue }) => {
      const s = getValue() as DemoPart["status"];
      return <StatusPill tone={STATUS_TONE[s]}>{s}</StatusPill>;
    },
  },
];

export default function DevUiPage() {
  const [qty, setQty] = React.useState<number | null>(250);
  const [date, setDate] = React.useState<Date | null>(new Date(2026, 10, 30));
  const [part, setPart] = React.useState<ComboboxOption | null>(null);
  const [category, setCategory] = React.useState<string | undefined>("passive");
  const [checked, setChecked] = React.useState(true);
  const [airGap, setAirGap] = React.useState(true);
  const [files, setFiles] = React.useState<File[]>([]);
  const rows = React.useMemo(() => demoParts(10_000), []);
  const photos = React.useMemo(
    () =>
      [
        ["Post-reflow top side", 215],
        ["AOI review U3", 190],
        ["Conformal coat UV check", 260],
        ["Packing label", 30],
      ].map(([label, hue], i) => ({
        id: `ph${i}`,
        src: demoPhotoSrc(String(label), Number(hue)),
        alt: String(label),
        caption: `SN-CPU1-2026-000${i + 1}`,
        meta: [
          { label: "Serial", value: `SN-CPU1-2026-000${i + 1}`, mono: true },
          { label: "Stage", value: String(label) },
          { label: "SHA-256", value: `3f9c${i}a71e…`, mono: true },
        ],
      })),
    [],
  );

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Developer" }, { label: "UI kit" }]}
        title="UI kit"
        description="Every FabTrack design-system component, with its states. Built from src/design/tokens.ts."
        primaryAction={
          <Button onClick={() => toast.success("Toast from the page's primary action")}>
            <PackageCheck /> Show toast
          </Button>
        }
      />

      <nav aria-label="UI kit sections" className="mb-6 flex flex-wrap gap-2" data-print="hide">
        {SECTIONS.map(([id, title]) => (
          <a key={id} href={`#${id}`} className="rounded-md border bg-white px-2.5 py-1 text-xs font-medium text-neutral-700 shadow-xs hover:border-neutral-300">
            {title}
          </a>
        ))}
      </nav>

      <div className="space-y-6">
        <Section id="buttons" title="Buttons">
          <Demo label="Variants">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">
              <Trash2 /> Danger
            </Button>
          </Demo>
          <Demo label="States and sizes">
            <Button loading>Saving</Button>
            <Button disabled>Disabled</Button>
            <Button size="sm" variant="secondary">
              Small
            </Button>
            <Button size="lg">Large</Button>
            <Button size="icon" variant="secondary" aria-label="Add line">
              <Plus />
            </Button>
          </Demo>
        </Section>

        <Section id="forms" title="Form controls">
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            <Field label="Project name" htmlFor="demo-name" hint="Shown on reports and POs" required>
              <Input placeholder="PLC I/O Expansion Rack" />
            </Field>
            <Field label="Client PO reference" htmlFor="demo-po" error="Client PO reference is required">
              <Input defaultValue="" placeholder="SPC/PO/2026/118" />
            </Field>
            <Field label="Disabled input" htmlFor="demo-disabled">
              <Input disabled defaultValue="PRJ-2026-0001" />
            </Field>
            <Field label="Build quantity" htmlFor="demo-qty" hint="Whole boards">
              <NumberInput value={qty} onValueChange={setQty} unit="pcs" min={0} max={100000} step={10} />
            </Field>
            <Field label="Category" htmlFor="demo-category">
              <Select
                value={category}
                onValueChange={setCategory}
                options={[
                  { value: "passive", label: "Passive" },
                  { value: "ic", label: "IC" },
                  { value: "connector", label: "Connector" },
                  { value: "pcb", label: "PCB", disabled: true },
                ]}
              />
            </Field>
            <Field label="Part (async search)" htmlFor="demo-part">
              <Combobox value={part} onChange={setPart} loadOptions={searchMpns} placeholder="Search MPN…" monoLabels />
            </Field>
            <Field label="Due date" htmlFor="demo-date">
              <DatePicker value={date} onChange={setDate} />
            </Field>
            <Field label="Notes" htmlFor="demo-notes" className="md:col-span-2">
              <Textarea placeholder="Notes for stores" rows={3} />
            </Field>
          </div>
          <Demo label="Checkbox and switch">
            <div className="flex items-center gap-2">
              <Checkbox id="demo-check" checked={checked} onCheckedChange={(v) => setChecked(v === true)} />
              <Label htmlFor="demo-check">Do not populate (DNP)</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="demo-check-disabled" disabled />
              <Label htmlFor="demo-check-disabled">Disabled</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="demo-switch" checked={airGap} onCheckedChange={setAirGap} />
              <Label htmlFor="demo-switch">Air-gapped mode</Label>
            </div>
          </Demo>
        </Section>

        <Section id="status" title="Badges and status">
          <Demo label="Status pills (semantic, app-wide)">
            {(Object.keys(TONE_MEANING) as StatusTone[]).map((t) => (
              <StatusPill key={t} tone={t}>
                {TONE_MEANING[t]}
              </StatusPill>
            ))}
          </Demo>
          <Demo label="Badges">
            <Badge>Rev B</Badge>
            <Badge tone="accent">Released</Badge>
            <Badge tone="teal">Clear to build</Badge>
            <Badge tone="outline">MSL 3</Badge>
          </Demo>
          <Demo label="Mono text (MPNs, serials, quantities)">
            <MonoText>STM32F407VGT6</MonoText>
            <MonoText>SN-CPU1-2026-00042</MonoText>
            <MonoText>1,250.0000 pcs</MonoText>
          </Demo>
        </Section>

        <Section id="cards" title="Cards and KPIs">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Lines fully received" value="86%" delta={4} deltaLabel=" pts" hint="vs last week" icon={<PackageCheck />} />
            <StatCard label="Overdue PO lines" value="7" delta={3} positiveIsGood={false} hint="vs last week" icon={<FileWarning />} />
            <StatCard label="Open NCRs" value="2" delta={0} hint="no change" icon={<Boxes />} />
            <StatCard label="First-pass yield" value="—" loading />
          </div>
        </Section>

        <Section id="navigation" title="Tabs, stepper, timeline">
          <Tabs defaultValue="overview">
            <TabsList aria-label="Project sections">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="boq">BOQ</TabsTrigger>
              <TabsTrigger value="qc">QC</TabsTrigger>
              <TabsTrigger value="history" disabled>
                History
              </TabsTrigger>
            </TabsList>
            <TabsContent value="overview">
              <p className="text-sm text-neutral-600">Overview tab content.</p>
            </TabsContent>
            <TabsContent value="boq">
              <p className="text-sm text-neutral-600">BOQ tab content.</p>
            </TabsContent>
            <TabsContent value="qc">
              <p className="text-sm text-neutral-600">QC tab content.</p>
            </TabsContent>
          </Tabs>
          <Stepper
            steps={[
              { id: "kit", label: "Kitting", state: "complete", detail: "50/50" },
              { id: "smt", label: "SMT", state: "complete", detail: "50/50" },
              { id: "reflow", label: "Reflow", state: "current", detail: "Awaiting QC" },
              { id: "aoi", label: "AOI", state: "upcoming" },
              { id: "tht", label: "THT", state: "blocked", detail: "Kit short" },
              { id: "pack", label: "Packing", state: "upcoming" },
            ]}
          />
          <Timeline
            events={[
              { id: "1", title: "BOQ Rev B released", timestamp: "2026-11-02T10:24:00+05:30", actor: "Priya (Project Manager)", tone: "green" },
              { id: "2", title: "PO-2026-0014 issued to Lakshmi Semiconductor", timestamp: "2026-11-01T16:05:00+05:30", actor: "Arjun (Purchase)", tone: "blue" },
              { id: "3", title: "NCR-2026-0003 raised: solder bridging on U1", timestamp: "2026-10-30T11:40:00+05:30", actor: "Meena (QC Inspector)", tone: "red", body: "Lot LOT-2026-0007, 3 boards affected." },
            ]}
          />
        </Section>

        <Section id="overlays" title="Dialog, drawer, toast, tooltip">
          <Demo label="Overlays">
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="secondary">Open dialog</Button>
              </DialogTrigger>
              <DialogContent
                title="Release BOQ revision B?"
                description="Revision A becomes read-only. This is recorded in the audit log."
                footer={<Button onClick={() => toast.success("Revision B released")}>Release</Button>}
              >
                <p className="text-sm text-neutral-600">42 lines, 3 changed from revision A.</p>
              </DialogContent>
            </Dialog>
            <Drawer>
              <DrawerTrigger asChild>
                <Button variant="secondary">Open drawer</Button>
              </DrawerTrigger>
              <DrawerContent title="BOQ line 12" description="GRM188R71H104KA93D" footer={<Button>Save line</Button>}>
                <p className="text-sm text-neutral-600">Drawer content for editing one record.</p>
              </DrawerContent>
            </Drawer>
            <Button variant="secondary" onClick={() => toast.success("GRN-2026-0008 posted", { description: "120 pcs accepted into STORES-A1" })}>
              Success toast
            </Button>
            <Button variant="secondary" onClick={() => toast.error("Could not post GRN", { description: "Quantity exceeds the open PO quantity" })}>
              Error toast
            </Button>
            <Tooltip content="Required qty includes 2% attrition">
              <Button variant="ghost">Hover for tooltip</Button>
            </Tooltip>
          </Demo>
        </Section>

        <Section id="feedback" title="Empty, skeleton, progress">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <EmptyState icon={Inbox} title="No purchase orders yet" description="Create a requisition from the BOQ shortfall to start ordering." action={<Button><Plus /> New requisition</Button>} />
            </Card>
            <Card className="space-y-3 p-5">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
              <ProgressBar label="Procurement progress" value={62} />
              <ProgressBar label="Production progress" value={35} tone="amber" />
              <ProgressBar label="QC progress" value={100} tone="green" />
            </Card>
          </div>
        </Section>

        <Section id="files" title="Files and photos">
          <FileDropzone
            onFiles={(f) => {
              setFiles(f);
              toast.success(`${f.length} file(s) ready to upload`);
            }}
            accept={["image/*", ".pdf"]}
            maxSizeBytes={25 * 1024 * 1024}
            hint="Images or PDF, up to 25 MB each"
          />
          {files.length > 0 && (
            <ul className="text-sm text-neutral-700">
              {files.map((f) => (
                <li key={f.name}>
                  <MonoText>{f.name}</MonoText> ({Math.ceil(f.size / 1024)} KB)
                </li>
              ))}
            </ul>
          )}
          <FileDropzone onFiles={() => undefined} disabled label="Uploads disabled" hint="Disabled state" />
          <PhotoGrid photos={photos} />
          <PhotoGrid photos={[]} emptyText="No photo evidence for this checklist item yet" />
        </Section>

        <Section id="table" title="Data table (10,000 rows)">
          <DataTable
            id="dev-ui-parts"
            data={rows}
            columns={PART_COLUMNS}
            getRowId={(r) => r.id}
            enableSelection
            exportFileName="ui-kit-parts"
            initialPinning={{ left: ["mpn"] }}
            maxHeight={420}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <DataTable id="dev-ui-loading" data={[] as DemoPart[]} columns={PART_COLUMNS.slice(0, 3)} getRowId={(r) => r.id} loading maxHeight={200} />
            <DataTable id="dev-ui-error" data={[] as DemoPart[]} columns={PART_COLUMNS.slice(0, 3)} getRowId={(r) => r.id} error="Could not load parts: the server returned 503" maxHeight={200} />
          </div>
        </Section>
      </div>
    </>
  );
}

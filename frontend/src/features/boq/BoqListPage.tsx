import type { ColumnDef } from "@tanstack/react-table";
import { ListChecks } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, Card, DataTable, EmptyState, MonoText, PageHeader, StatusPill } from "@/design/components";
import { fmtDate } from "@/lib/format";

import { type Boq, REVISION_TONE, useAllBoqs } from "./api";

function current(b: Boq) {
  return b.revisions.find((r) => r.status === "released") ?? b.revisions[b.revisions.length - 1] ?? null;
}

const columns: ColumnDef<Boq, unknown>[] = [
  {
    accessorKey: "project_code",
    header: "Project",
    size: 150,
    meta: { mono: true },
    cell: ({ row }) => (
      <Link to={`/projects/${row.original.project_id}?tab=boq`} className="font-mono text-accent-700 hover:underline">
        {row.original.project_code}
      </Link>
    ),
  },
  { accessorKey: "project_name", header: "Project name", size: 220 },
  { accessorKey: "name", header: "BOQ", size: 220 },
  { id: "scope", header: "Module / assembly", size: 180, accessorFn: (b) => [b.module_code, b.assembly_label].filter(Boolean).join(" · ") || "Whole project" },
  {
    id: "rev",
    header: "Current revision",
    size: 170,
    accessorFn: (b) => current(b)?.revision ?? "",
    cell: ({ row }) => {
      const r = current(row.original);
      return r ? (
        <span className="inline-flex items-center gap-2">
          <MonoText>{r.revision}</MonoText>
          <StatusPill tone={REVISION_TONE[r.status]}>{r.status}</StatusPill>
        </span>
      ) : (
        "—"
      );
    },
  },
  { id: "lines", header: "Lines", size: 80, meta: { mono: true, align: "right", exportType: "number" }, accessorFn: (b) => current(b)?.line_count ?? 0 },
  { id: "build", header: "Build qty", size: 90, meta: { mono: true, align: "right", exportType: "number" }, accessorFn: (b) => current(b)?.build_qty ?? 0 },
  { id: "released", header: "Released", size: 120, meta: { mono: true }, accessorFn: (b) => fmtDate(current(b)?.released_at) },
];

export default function BoqListPage() {
  const boqs = useAllBoqs();
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "BOQ" }]}
        title="Bills of quantity"
        description="Every BOQ across your projects. Open a project's BOQ tab to edit, import or compare revisions."
        primaryAction={
          <Button asChild variant="secondary">
            <Link to="/projects">Go to projects</Link>
          </Button>
        }
      />
      {boqs.isError ? (
        <Card>
          <EmptyState title="Could not load BOQs" description={boqs.error.message} />
        </Card>
      ) : (
        <DataTable
          id="all-boqs"
          data={boqs.data ?? []}
          columns={columns}
          getRowId={(b) => b.id}
          loading={boqs.isPending}
          exportFileName="boqs"
          emptyState={<EmptyState icon={ListChecks} title="No BOQs yet" description="Create one from a project's BOQ tab." action={<Button asChild><Link to="/projects">Open projects</Link></Button>} />}
        />
      )}
    </>
  );
}

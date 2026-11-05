import type { ColumnDef } from "@tanstack/react-table";
import { addDays, format } from "date-fns";
import { Building2, FolderKanban, Plus, RotateCcw } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge, Button, Card, DataTable, EmptyState, Field, Input, PageHeader, Select, Skeleton, StatusPill } from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { fmtDate } from "@/lib/format";

import { useCurrentDivision } from "./DivisionContext";
import { DivisionsDrawer, ProjectDrawer } from "./ProjectForms";
import { PROJECT_STATUSES, type Project, type ProjectFilters, statusInfo, useDivisionsQuery, useProjects, useStaff } from "./api";

const ANY = "__any";
const OPEN = "draft,active,on_hold";

const DUE_WINDOWS = [
  { value: ANY, label: "Any due date" },
  { value: "overdue", label: "Overdue" },
  { value: "30", label: "Due in 30 days" },
  { value: "90", label: "Due in 90 days" },
];

function dueFilters(window: string): Pick<ProjectFilters, "overdue" | "due_after" | "due_before"> {
  if (window === "overdue") return { overdue: true };
  if (window === "30" || window === "90") {
    const today = new Date();
    return { due_after: format(today, "yyyy-MM-dd"), due_before: format(addDays(today, Number(window)), "yyyy-MM-dd") };
  }
  return {};
}

export function isOverdue(p: Pick<Project, "due_date" | "status">): boolean {
  return !!p.due_date && ["draft", "active", "on_hold"].includes(p.status) && new Date(`${p.due_date}T23:59:59`) < new Date();
}

const columns: ColumnDef<Project, unknown>[] = [
  {
    accessorKey: "code",
    header: "Project",
    size: 150,
    meta: { mono: true },
    cell: ({ row }) => (
      <Link to={`/projects/${row.original.id}`} className="font-mono text-accent-700 hover:underline">
        {row.original.code}
      </Link>
    ),
  },
  { accessorKey: "name", header: "Name", size: 260 },
  { accessorKey: "client_name", header: "Client", size: 220 },
  {
    accessorKey: "status",
    header: "Status",
    size: 130,
    meta: { exportValue: (p: Project) => statusInfo(p.status).label },
    cell: ({ row }) => {
      const s = statusInfo(row.original.status);
      return <StatusPill tone={s.tone}>{s.label}</StatusPill>;
    },
  },
  { id: "pm", header: "Project manager", size: 170, accessorFn: (p) => p.project_manager_name ?? "—" },
  {
    accessorKey: "due_date",
    header: "Due",
    size: 140,
    meta: { mono: true },
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1.5">
        {fmtDate(row.original.due_date)}
        {isOverdue(row.original) && <StatusPill tone="red">Overdue</StatusPill>}
      </span>
    ),
  },
  { accessorKey: "module_count", header: "Modules", size: 90, meta: { mono: true, align: "right", exportType: "number" } },
];

export default function ProjectsPage() {
  const navigate = useNavigate();
  const canManage = useCan("projects:manage");
  const { divisionId } = useCurrentDivision();
  const divisions = useDivisionsQuery();
  const staff = useStaff(useCan("directory:read"));
  const [status, setStatus] = React.useState<string>(OPEN);
  const [pm, setPm] = React.useState<string>(ANY);
  const [client, setClient] = React.useState("");
  const [due, setDue] = React.useState<string>(ANY);
  const [drawer, setDrawer] = React.useState(false);
  const [divisionsOpen, setDivisionsOpen] = React.useState(false);

  const filters: ProjectFilters = {
    status: status === ANY ? undefined : status,
    project_manager_id: pm === ANY ? undefined : pm,
    client: client.trim() || undefined,
    division_id: divisionId ?? undefined,
    ...dueFilters(due),
  };
  const projects = useProjects(filters);

  const groups = React.useMemo(() => {
    const byDivision = new Map<string, Project[]>();
    for (const p of projects.data?.items ?? []) byDivision.set(p.division_id, [...(byDivision.get(p.division_id) ?? []), p]);
    return (divisions.data ?? [])
      .filter((d) => !divisionId || d.id === divisionId)
      .map((d) => ({ division: d, projects: byDivision.get(d.id) ?? [] }));
  }, [projects.data, divisions.data, divisionId]);

  const reset = () => {
    setStatus(OPEN);
    setPm(ANY);
    setClient("");
    setDue(ANY);
  };

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Projects" }]}
        title="Projects"
        description="Every project by division, with its client, status and due date."
        secondaryActions={
          <Button variant="secondary" onClick={() => setDivisionsOpen(true)}>
            <Building2 /> Divisions
          </Button>
        }
        primaryAction={
          canManage && (
            <Button onClick={() => setDrawer(true)} disabled={!divisions.data?.length}>
              <Plus /> New project
            </Button>
          )
        }
      />

      <div className="mb-5 grid gap-3 rounded-lg border bg-white p-4 shadow-xs sm:grid-cols-2 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto]" role="search" aria-label="Project filters">
        <Field label="Status" htmlFor="f-status">
          <Select
            value={status}
            onValueChange={setStatus}
            options={[{ value: OPEN, label: "Open (draft, active, on hold)" }, { value: ANY, label: "All statuses" }, ...PROJECT_STATUSES.map((s) => ({ value: s.value, label: s.label }))]}
          />
        </Field>
        <Field label="Project manager" htmlFor="f-pm">
          <Select
            value={pm}
            onValueChange={setPm}
            options={[{ value: ANY, label: "Anyone" }, ...(staff.data ?? []).filter((u) => u.roles.includes("project_manager") || u.roles.includes("admin")).map((u) => ({ value: u.id, label: u.full_name }))]}
          />
        </Field>
        <Field label="Client" htmlFor="f-client">
          <Input placeholder="Client name contains…" value={client} onChange={(e) => setClient(e.target.value)} />
        </Field>
        <Field label="Due" htmlFor="f-due">
          <Select value={due} onValueChange={setDue} options={DUE_WINDOWS} />
        </Field>
        <div className="flex items-end">
          <Button variant="ghost" onClick={reset}>
            <RotateCcw /> Reset
          </Button>
        </div>
      </div>

      {projects.isPending || divisions.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      ) : projects.isError ? (
        <Card>
          <EmptyState title="Could not load projects" description={projects.error.message} />
        </Card>
      ) : groups.length === 0 ? (
        <Card>
          <EmptyState
            icon={Building2}
            title="No divisions yet"
            description="Projects belong to a division. Create the first division to start."
            action={<Button onClick={() => setDivisionsOpen(true)}><Plus /> Add a division</Button>}
          />
        </Card>
      ) : (
        <div className="space-y-6">
          {groups.map(({ division, projects: list }) => (
            <section key={division.id} aria-labelledby={`div-${division.id}`}>
              <div className="mb-2 flex items-center gap-2">
                <h2 id={`div-${division.id}`} className="text-md font-semibold text-neutral-900">
                  {division.name}
                </h2>
                <Badge tone="outline" className="font-mono">{division.code}</Badge>
                <span className="text-xs text-neutral-500">{list.length} project{list.length === 1 ? "" : "s"}</span>
              </div>
              <DataTable
                id={`projects-${division.code}`}
                data={list}
                columns={columns}
                getRowId={(p) => p.id}
                exportFileName={`projects-${division.code}`}
                maxHeight={420}
                emptyState={
                  <EmptyState
                    icon={FolderKanban}
                    title="No projects match"
                    description="Change the filters, or create a project in this division."
                    action={canManage && <Button variant="secondary" onClick={() => setDrawer(true)}><Plus /> New project</Button>}
                    className="py-8"
                  />
                }
              />
            </section>
          ))}
        </div>
      )}

      <ProjectDrawer open={drawer} project={null} defaultDivisionId={divisionId} onClose={() => setDrawer(false)} onSaved={(p) => navigate(`/projects/${p.id}`)} />
      <DivisionsDrawer open={divisionsOpen} onClose={() => setDivisionsOpen(false)} />
    </>
  );
}

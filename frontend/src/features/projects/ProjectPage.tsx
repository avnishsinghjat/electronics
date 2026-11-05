import { CircuitBoard, Copy, History, Layers, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { PROJECT_TABS } from "@/app/features";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  Dialog,
  DialogContent,
  EmptyState,
  MonoText,
  PageHeader,
  Skeleton,
  StatusPill,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Timeline,
  type TimelineEvent,
  toast,
} from "@/design/components";
import type { StatusTone } from "@/design/tokens";
import { Attachments } from "@/features/attachments/Attachments";
import { BoqPanel } from "@/features/boq/BoqPanel";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { readPref } from "@/lib/storage";

import { CloneDialog, ProjectDrawer } from "./ProjectForms";
import { isOverdue } from "./ProjectsPage";
import { AssemblyDrawer, ModuleDrawer, useStructureDrawers } from "./StructureForms";
import { type Assembly, type Module, type ProjectTree, statusInfo, useOrgMutations, useProjectHistory, useProjectTree } from "./api";

const ACTION_LABEL: Record<string, string> = { insert: "created", update: "updated", soft_delete: "deleted", restore: "restored", delete: "removed" };
const ACTION_TONE: Record<string, StatusTone> = { insert: "green", update: "blue", soft_delete: "red", restore: "blue", delete: "red" };

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-neutral-900">{children}</dd>
    </div>
  );
}

function ConfirmDelete({ what, onConfirm, onClose, pending }: { what: string | null; onConfirm: () => void; onClose: () => void; pending: boolean }) {
  return (
    <Dialog open={what !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={`Delete ${what ?? ""}?`}
        description="It is hidden everywhere; the deletion is recorded in the project history."
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button variant="danger" loading={pending} onClick={onConfirm}>Delete</Button>
          </>
        }
      />
    </Dialog>
  );
}

function Structure({ tree }: { tree: ProjectTree }) {
  const canManage = useCan("projects:manage");
  const { moduleDrawer, setModuleDrawer, assemblyDrawer, setAssemblyDrawer } = useStructureDrawers();
  const { deleteModule, deleteAssembly } = useOrgMutations();
  const [pending, setPending] = React.useState<{ kind: "module"; item: Module } | { kind: "assembly"; item: Assembly } | null>(null);

  const doDelete = () => {
    if (!pending) return;
    const mutation = pending.kind === "module" ? deleteModule : deleteAssembly;
    mutation.mutate(
      { id: pending.item.id, row_version: pending.item.row_version },
      {
        onSuccess: () => toast.success(`${pending.kind === "module" ? "Module" : "Assembly"} deleted`),
        onError: (err) => toast.error(err instanceof ApiError ? err.message : "Could not delete"),
        onSettled: () => setPending(null),
      },
    );
  };

  return (
    <Card>
      <CardHeader
        title="Modules and PCB assemblies"
        description="What this project delivers, and the board revisions inside each module."
        actions={canManage && <Button size="sm" onClick={() => setModuleDrawer({ module: null })}><Plus /> Add module</Button>}
      />
      <CardContent className="space-y-4">
        {tree.modules.length === 0 ? (
          <EmptyState
            icon={Layers}
            title="No modules yet"
            description="Add the deliverable units of this project, then the PCB assemblies inside each."
            action={canManage && <Button onClick={() => setModuleDrawer({ module: null })}><Plus /> Add module</Button>}
            className="py-8"
          />
        ) : (
          tree.modules.map((m) => (
            <section key={m.id} aria-label={`Module ${m.code}`} className="rounded-lg border">
              <div className="flex flex-wrap items-center gap-3 border-b bg-neutral-25 px-4 py-2.5">
                <MonoText className="font-semibold text-neutral-900">{m.code}</MonoText>
                <span className="text-sm text-neutral-800">{m.name}</span>
                <Badge tone="outline">
                  <MonoText>{m.qty_to_deliver}</MonoText> to deliver
                </Badge>
                {canManage && (
                  <span className="ml-auto flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => setAssemblyDrawer({ moduleId: m.id, assembly: null })}>
                      <Plus /> Assembly
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label={`Edit module ${m.code}`} onClick={() => setModuleDrawer({ module: m })}>
                      <Pencil />
                    </Button>
                    <Button size="icon-sm" variant="ghost" aria-label={`Delete module ${m.code}`} onClick={() => setPending({ kind: "module", item: m })}>
                      <Trash2 />
                    </Button>
                  </span>
                )}
              </div>
              {m.assemblies.length === 0 ? (
                <p className="px-4 py-3 text-sm text-neutral-500">No PCB assemblies in this module yet.</p>
              ) : (
                <table className="w-full table-fixed text-sm" aria-label={`Assemblies of ${m.code}`}>
                  <colgroup>
                    <col className="w-[18%]" />
                    <col className="w-[26%]" />
                    <col className="w-[9%]" />
                    <col className="w-[13%]" />
                    <col className="w-[13%]" />
                    <col className="w-[11%]" />
                    {canManage && <col className="w-[10%]" />}
                  </colgroup>
                  <thead className="text-left text-xs font-semibold text-neutral-600">
                    <tr className="border-b">
                      <th scope="col" className="px-4 py-2">Assembly</th>
                      <th scope="col" className="px-2 py-2">Board</th>
                      <th scope="col" className="px-2 py-2">Layers</th>
                      <th scope="col" className="px-2 py-2">Size (mm)</th>
                      <th scope="col" className="px-2 py-2">Finish</th>
                      <th scope="col" className="px-2 py-2">Files</th>
                      {canManage && <th scope="col" className="px-4 py-2"><span className="sr-only">Actions</span></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {m.assemblies.map((a) => (
                      <tr key={a.id} className="border-b border-neutral-100 last:border-0">
                        <td className="px-4 py-2"><MonoText>{a.code}</MonoText> <Badge>rev {a.revision}</Badge></td>
                        <td className="truncate px-2 py-2">{a.board_name}{a.qty_per_module > 1 && <span className="text-neutral-500"> ×{a.qty_per_module}</span>}</td>
                        <td className="px-2 py-2 font-mono tabular-nums">{a.layer_count}</td>
                        <td className="px-2 py-2 font-mono tabular-nums">{a.size_x_mm && a.size_y_mm ? `${Number(a.size_x_mm)} × ${Number(a.size_y_mm)}` : "—"}</td>
                        <td className="px-2 py-2">{a.finish ?? "—"}</td>
                        <td className="px-2 py-2 text-xs text-neutral-600">
                          {[a.assembly_drawing_file_id && "Drawing", a.kicad_project_file_id && "KiCad"].filter(Boolean).join(" · ") || "—"}
                        </td>
                        {canManage && (
                          <td className="px-4 py-1 text-right">
                            <Button size="icon-sm" variant="ghost" aria-label={`Edit assembly ${a.code} rev ${a.revision}`} onClick={() => setAssemblyDrawer({ moduleId: m.id, assembly: a })}>
                              <Pencil />
                            </Button>
                            <Button size="icon-sm" variant="ghost" aria-label={`Delete assembly ${a.code} rev ${a.revision}`} onClick={() => setPending({ kind: "assembly", item: a })}>
                              <Trash2 />
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          ))
        )}
      </CardContent>
      <ModuleDrawer open={moduleDrawer !== null} projectId={tree.project.id} module={moduleDrawer?.module ?? null} onClose={() => setModuleDrawer(null)} />
      <AssemblyDrawer open={assemblyDrawer !== null} moduleId={assemblyDrawer?.moduleId ?? ""} assembly={assemblyDrawer?.assembly ?? null} onClose={() => setAssemblyDrawer(null)} />
      <ConfirmDelete
        what={pending ? (pending.kind === "module" ? `module ${pending.item.code}` : `assembly ${pending.item.code} rev ${(pending.item as Assembly).revision}`) : null}
        pending={deleteModule.isPending || deleteAssembly.isPending}
        onConfirm={doDelete}
        onClose={() => setPending(null)}
      />
    </Card>
  );
}

function HistoryTab({ projectId }: { projectId: string }) {
  const history = useProjectHistory(projectId, true);
  if (history.isPending) return <Skeleton className="h-48" />;
  if (history.isError) return <p role="alert" className="text-sm text-status-red-fg">{history.error.message}</p>;
  if (history.data.length === 0) return <EmptyState icon={History} title="No history yet" />;
  const events: TimelineEvent[] = history.data.map((h) => ({
    id: String(h.id),
    title: `${h.label} ${ACTION_LABEL[h.action] ?? h.action}`,
    timestamp: h.occurred_at,
    actor: h.actor_name ?? "System",
    tone: ACTION_TONE[h.action] ?? "grey",
    body: h.changed_fields?.length ? <span className="text-xs text-neutral-600">Changed: {h.changed_fields.join(", ")}</span> : undefined,
  }));
  return (
    <Card>
      <CardContent>
        <Timeline events={events} />
      </CardContent>
    </Card>
  );
}

function RoadmapTab({ label, phase }: { label: string; phase: number }) {
  return (
    <Card>
      <EmptyState icon={CircuitBoard} title={`${label} for this project is delivered in Phase ${phase}`} description="This tab opens when that phase's gate passes." />
    </Card>
  );
}

export default function ProjectPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const canManage = useCan("projects:manage");
  const canHistory = useCan("projects:history");
  const canBoq = useCan("boq:read");
  const tree = useProjectTree(projectId);
  const { deleteProject } = useOrgMutations();
  const [editing, setEditing] = React.useState(false);
  const [cloning, setCloning] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const preview = readPref("preview-tabs") === "1";
  const tab = params.get("tab") ?? "overview";

  if (tree.isPending) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (tree.isError) {
    return (
      <Card className="mx-auto mt-12 max-w-xl">
        <EmptyState
          title={tree.error instanceof ApiError && tree.error.status === 404 ? "Project not found" : "Could not load the project"}
          description={tree.error.message}
          action={<Button variant="secondary" onClick={() => navigate("/projects")}>Back to projects</Button>}
        />
      </Card>
    );
  }

  const p = tree.data.project;
  const s = statusInfo(p.status);
  const extraTabs = Object.entries(PROJECT_TABS).filter(([key, t]) => (t.live && (key !== "boq" || canBoq)) || preview);

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Projects", to: "/projects" }, { label: p.code }]}
        title={p.name}
        meta={
          <>
            <MonoText className="text-neutral-600">{p.code}</MonoText>
            <StatusPill tone={s.tone}>{s.label}</StatusPill>
            {isOverdue(p) && <StatusPill tone="red">Overdue</StatusPill>}
            {p.is_sample && <Badge tone="outline">Sample data</Badge>}
          </>
        }
        secondaryActions={
          canManage && (
            <>
              <Button variant="secondary" onClick={() => setCloning(true)}>
                <Copy /> Clone
              </Button>
              <Button variant="ghost" size="icon" aria-label="Delete project" onClick={() => setDeleting(true)}>
                <Trash2 />
              </Button>
            </>
          )
        }
        primaryAction={canManage && <Button onClick={() => setEditing(true)}><Pencil /> Edit project</Button>}
      />

      <Tabs value={tab} onValueChange={(v) => setParams(v === "overview" ? {} : { tab: v }, { replace: true })}>
        <TabsList aria-label="Project sections">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          {extraTabs.map(([key, t]) => (
            <TabsTrigger key={key} value={key}>{t.label}</TabsTrigger>
          ))}
          <TabsTrigger value="files">Files</TabsTrigger>
          {canHistory && <TabsTrigger value="history">History</TabsTrigger>}
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <Card>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
                <Detail label="Client">{p.client_name}</Detail>
                <Detail label="Client PO reference">{p.client_po_ref ? <MonoText>{p.client_po_ref}</MonoText> : "—"}</Detail>
                <Detail label="Division">{p.division_name}</Detail>
                <Detail label="Project manager">{p.project_manager_name ?? "Not assigned"}</Detail>
                <Detail label="Start date"><MonoText>{fmtDate(p.start_date)}</MonoText></Detail>
                <Detail label="Due date"><MonoText>{fmtDate(p.due_date)}</MonoText></Detail>
                <Detail label="Modules"><MonoText>{tree.data.modules.length}</MonoText></Detail>
                <Detail label="PCB assemblies"><MonoText>{tree.data.modules.reduce((n, m) => n + m.assemblies.length, 0)}</MonoText></Detail>
                {p.notes && <div className="sm:col-span-2 lg:col-span-4"><Detail label="Notes"><span className="whitespace-pre-line">{p.notes}</span></Detail></div>}
              </dl>
            </CardContent>
          </Card>
          <Structure tree={tree.data} />
        </TabsContent>

        {extraTabs.map(([key, t]) => (
          <TabsContent key={key} value={key}>
            {key === "boq" && t.live ? <BoqPanel tree={tree.data} /> : <RoadmapTab label={t.label} phase={t.phase} />}
          </TabsContent>
        ))}

        <TabsContent value="files">
          <Card>
            <CardHeader title="Project files" description="Client specifications, purchase orders, approvals and drawings for the whole project." />
            <CardContent>
              <Attachments refType="project" refId={p.id} title="Project files" />
            </CardContent>
          </Card>
        </TabsContent>

        {canHistory && (
          <TabsContent value="history">
            <HistoryTab projectId={p.id} />
          </TabsContent>
        )}
      </Tabs>

      <ProjectDrawer open={editing} project={p} onClose={() => setEditing(false)} />
      <CloneDialog project={p} open={cloning} onClose={() => setCloning(false)} onCloned={(c) => { setCloning(false); navigate(`/projects/${c.id}`); }} />
      <ConfirmDelete
        what={deleting ? `project ${p.code}` : null}
        pending={deleteProject.isPending}
        onClose={() => setDeleting(false)}
        onConfirm={() =>
          deleteProject.mutate(
            { id: p.id, row_version: p.row_version },
            {
              onSuccess: () => {
                toast.success(`${p.code} deleted`);
                navigate("/projects");
              },
              onError: (err) => {
                toast.error(err instanceof ApiError ? err.message : "Could not delete");
                setDeleting(false);
              },
            },
          )
        }
      />
    </>
  );
}

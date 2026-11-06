import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { isOverdue } from "@/features/projects/ProjectsPage";
import type { Assembly, Division, Project, ProjectTree } from "@/features/projects/api";

import { type Handler, jsonResponse, makeMe, mockApi, renderAt, signedInRoutes } from "./utils";

const DIVS: Division[] = [
  { id: "d1", code: "IND", name: "Industrial", description: null, is_sample: false, row_version: 1 },
  { id: "d2", code: "PWR", name: "Power", description: null, is_sample: false, row_version: 1 },
];

function project(p: Partial<Project>): Project {
  return {
    id: "p1", division_id: "d1", code: "PRJ-2026-0001", name: "PLC Rack", client_name: "Sahyadri", client_po_ref: "SC/1",
    start_date: "2026-09-01", due_date: "2099-12-31", status: "active", project_manager_id: null, notes: null, is_sample: false,
    row_version: 3, created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z", division_code: "IND",
    division_name: "Industrial", project_manager_name: null, module_count: 1, ...p,
  };
}

const ASM: Assembly = {
  id: "a1", module_id: "m1", code: "CPU1", board_name: "CPU board", revision: "B", qty_per_module: 1, layer_count: 4,
  size_x_mm: "100.00", size_y_mm: "80.00", finish: "ENIG", kicad_project_file_id: null, assembly_drawing_file_id: "f1",
  stage_template_id: "t1", notes: null, row_version: 2,
};

const TREE: ProjectTree = {
  project: project({}),
  modules: [{ id: "m1", project_id: "p1", code: "MOD-CPU", name: "CPU module", qty_to_deliver: 25, description: null, row_version: 1, assemblies: [ASM] }],
};

const STAFF = [{ id: "u-pm", username: "priya", full_name: "Priya PM", roles: ["project_manager"] }];

function base(extra: Record<string, Handler> = {}) {
  return signedInRoutes(makeMe(), {
    "GET /divisions": () => DIVS,
    "GET /directory/users": () => STAFF,
    "GET /stage-templates": () => [{ id: "t1", name: "Standard PCBA", is_default: true }],
    ...extra,
  });
}

describe("Projects list", () => {
  it("groups projects by division and sends filters to the API", async () => {
    const { calls } = mockApi(
      base({
        "GET /projects": () => ({
          items: [project({}), project({ id: "p2", code: "PRJ-2026-0002", name: "Late job", due_date: "2020-01-01" }), project({ id: "p3", division_id: "d2", code: "PRJ-2026-0003", name: "BMS", division_code: "PWR" })],
          total: 3, page: 1, page_size: 500,
        }),
      }),
    );
    renderAt("/projects");
    const ind = await screen.findByRole("region", { name: /Industrial/ });
    expect(within(ind).getByRole("link", { name: "PRJ-2026-0001" })).toHaveAttribute("href", "/projects/p1");
    expect(within(ind).getByText("Overdue")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /Power/ })).getByText("BMS")).toBeInTheDocument();
    expect(calls.find((c) => c.path.startsWith("/projects?"))?.path).toContain("status=draft%2Cactive%2Con_hold");

    await userEvent.click(screen.getByRole("combobox", { name: "Due" }));
    await userEvent.click(await screen.findByRole("option", { name: "Overdue" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("overdue=true"))).toBe(true));
    await userEvent.type(screen.getByLabelText("Client"), "sahy");
    await waitFor(() => expect(calls.some((c) => c.path.includes("client=sahy"))).toBe(true));
  });

  it("creates a project from the drawer with validation", async () => {
    let created: unknown = null;
    mockApi(
      base({
        "GET /projects": () => ({ items: [], total: 0, page: 1, page_size: 500 }),
        "POST /projects": ({ body }) => {
          created = body;
          return project({ id: "new", code: "PRJ-2026-0009", name: "New job" });
        },
        "GET /projects/new/tree": () => ({ project: project({ id: "new", code: "PRJ-2026-0009", name: "New job", module_count: 0 }), modules: [] }),
      }),
    );
    const router = renderAt("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "New project" }));
    const drawer = await screen.findByRole("dialog", { name: "New project" });
    await userEvent.click(within(drawer).getByRole("button", { name: "Create project" }));
    expect(await within(drawer).findByText("Enter the project name")).toBeInTheDocument();
    await userEvent.type(within(drawer).getByLabelText(/Project name/), "New job");
    await userEvent.type(within(drawer).getByLabelText(/^Client\*?$/), "Konkan");
    await userEvent.type(within(drawer).getByLabelText("Start date"), "2026-12-01{Enter}");
    await userEvent.type(within(drawer).getByLabelText("Due date"), "2026-11-01{Enter}");
    await userEvent.click(within(drawer).getByRole("button", { name: "Create project" }));
    expect(await within(drawer).findByText("Due date is before the start date")).toBeInTheDocument();
    await userEvent.clear(within(drawer).getByLabelText("Due date"));
    await userEvent.type(within(drawer).getByLabelText("Due date"), "2027-01-15{Enter}");
    await userEvent.click(within(drawer).getByRole("combobox", { name: "Project manager" }));
    await userEvent.click(await screen.findByRole("option", { name: "Priya PM" }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/new"));
    expect(created).toEqual({
      division_id: "d1", name: "New job", client_name: "Konkan", client_po_ref: null, start_date: "2026-12-01",
      due_date: "2027-01-15", status: "draft", project_manager_id: "u-pm", notes: null,
    });
  });

  it("hides create actions from read-only users", async () => {
    mockApi(signedInRoutes(makeMe({ roles: ["stores"], permissions: ["projects:read", "dashboard:read", "directory:read"] }), {
      "GET /divisions": () => DIVS,
      "GET /directory/users": () => STAFF,
      "GET /projects": () => ({ items: [project({})], total: 1, page: 1, page_size: 500 }),
    }));
    renderAt("/projects");
    expect(await screen.findByText("PLC Rack")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New project" })).not.toBeInTheDocument();
  });

  it("computes overdue only for open projects", () => {
    expect(isOverdue({ due_date: "2020-01-01", status: "active" })).toBe(true);
    expect(isOverdue({ due_date: "2020-01-01", status: "completed" })).toBe(false);
    expect(isOverdue({ due_date: "2099-01-01", status: "active" })).toBe(false);
    expect(isOverdue({ due_date: null, status: "active" })).toBe(false);
  });
});

describe("Project page", () => {
  it("shows details, structure, files and history tabs; unbuilt tabs stay hidden", async () => {
    mockApi(
      base({
        "GET /projects/p1/tree": () => TREE,
        "GET /files": () => [],
        "GET /projects/p1/history": () => [
          { id: 2, occurred_at: "2026-11-04T10:00:00Z", actor_name: "Priya PM", action: "update", entity_type: "projects", entity_id: "p1", label: "Project PRJ-2026-0001", changed_fields: ["status"] },
          { id: 1, occurred_at: "2026-11-03T10:00:00Z", actor_name: "Priya PM", action: "insert", entity_type: "modules", entity_id: "m1", label: "Module MOD-CPU", changed_fields: null },
        ],
      }),
    );
    renderAt("/projects/p1");
    expect(await screen.findByRole("heading", { level: 1, name: "PLC Rack" })).toBeInTheDocument();
    const tabs = screen.getByRole("tablist", { name: "Project sections" });
    expect(within(tabs).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Overview", "BOQ", "Procurement", "Production", "Files", "History"]);
    const structure = screen.getByRole("region", { name: "Module MOD-CPU" });
    expect(within(structure).getByText("CPU board")).toBeInTheDocument();
    expect(within(structure).getByText("100 × 80")).toBeInTheDocument();
    expect(within(structure).getByText("Drawing")).toBeInTheDocument();

    await userEvent.click(within(tabs).getByRole("tab", { name: "History" }));
    expect(await screen.findByText("Project PRJ-2026-0001 updated")).toBeInTheDocument();
    expect(screen.getByText("Changed: status")).toBeInTheDocument();
    expect(screen.getByText("Module MOD-CPU created")).toBeInTheDocument();
  });

  it("previews unbuilt tabs with the phase that delivers them when enabled", async () => {
    localStorage.setItem("fabtrack.preview-tabs", "1");
    mockApi(base({ "GET /projects/p1/tree": () => TREE }));
    renderAt("/projects/p1?tab=qc");
    expect(await screen.findByRole("heading", { name: "QC for this project is delivered in Phase 8" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Overview", "BOQ", "Procurement", "Production", "QC", "Documents", "Files", "History"]);
  });

  it("adds a module and an assembly", async () => {
    let moduleBody: unknown = null;
    let assemblyBody: unknown = null;
    mockApi(
      base({
        "GET /projects/p1/tree": () => TREE,
        "POST /projects/p1/modules": ({ body }) => {
          moduleBody = body;
          return { id: "m2", project_id: "p1", code: "MOD-IO", name: "IO", qty_to_deliver: 40, description: null, row_version: 1 };
        },
        "POST /modules/m1/assemblies": ({ body }) => {
          assemblyBody = body;
          return { ...ASM, id: "a2", code: "PSU", revision: "A" };
        },
      }),
    );
    renderAt("/projects/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Add module" }));
    const md = await screen.findByRole("dialog", { name: "New module" });
    await userEvent.type(within(md).getByLabelText(/Code/), "MOD-IO");
    await userEvent.type(within(md).getByLabelText(/^Name/), "IO");
    const qty = within(md).getByLabelText(/Quantity to deliver/);
    await userEvent.clear(qty);
    await userEvent.type(qty, "40{Enter}");
    await userEvent.click(within(md).getByRole("button", { name: "Add module" }));
    await waitFor(() => expect(moduleBody).toEqual({ code: "MOD-IO", name: "IO", qty_to_deliver: 40, description: null }));

    const structure = screen.getByRole("region", { name: "Module MOD-CPU" });
    await userEvent.click(within(structure).getByRole("button", { name: /Assembly/ }));
    const ad = await screen.findByRole("dialog", { name: "New PCB assembly" });
    expect(within(ad).getByText(/Save the assembly first/)).toBeInTheDocument();
    await userEvent.type(within(ad).getByLabelText(/Assembly code/), "PSU");
    await userEvent.type(within(ad).getByLabelText(/Board name/), "Power board");
    await userEvent.type(within(ad).getByLabelText("Width"), "abc");
    await userEvent.click(within(ad).getByRole("button", { name: "Add assembly" }));
    expect(await within(ad).findByText("Positive number, up to 2 decimals")).toBeInTheDocument();
    await userEvent.clear(within(ad).getByLabelText("Width"));
    await userEvent.type(within(ad).getByLabelText("Width"), "75.5");
    await userEvent.click(within(ad).getByRole("button", { name: "Add assembly" }));
    await waitFor(() =>
      expect(assemblyBody).toEqual({
        code: "PSU", board_name: "Power board", revision: "A", qty_per_module: 1, layer_count: 2, size_x_mm: "75.5",
        size_y_mm: null, finish: null, stage_template_id: null, notes: null,
      }),
    );
  });

  it("clones a project and opens the copy", async () => {
    let cloneBody: unknown = null;
    mockApi(
      base({
        "GET /projects/p1/tree": () => TREE,
        "POST /projects/p1/clone": ({ body }) => {
          cloneBody = body;
          return project({ id: "p9", code: "PRJ-2026-0009", name: "PLC Rack (repeat)" });
        },
        "GET /projects/p9/tree": () => ({ ...TREE, project: project({ id: "p9", code: "PRJ-2026-0009", name: "PLC Rack (repeat)" }) }),
      }),
    );
    const router = renderAt("/projects/p1");
    await userEvent.click(await screen.findByRole("button", { name: "Clone" }));
    const dlg = await screen.findByRole("dialog", { name: "Clone PRJ-2026-0001" });
    await userEvent.type(within(dlg).getByLabelText("Client PO reference"), "SC/2");
    await userEvent.click(within(dlg).getByRole("button", { name: "Create copy" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/p9"));
    expect(cloneBody).toEqual({ name: "PLC Rack (repeat)", client_po_ref: "SC/2", start_date: null, due_date: null, include_boq: true });
  });

  it("shows not found for a project outside the user's scope", async () => {
    mockApi(base({ "GET /projects/zzz/tree": () => jsonResponse({ error: { code: "not_found", message: "Project not found", details: null } }, 404) }));
    renderAt("/projects/zzz");
    expect(await screen.findByRole("heading", { name: "Project not found" })).toBeInTheDocument();
  });
});

describe("Attachments", () => {
  it("uploads, lists, and deletes a file with confirmation", async () => {
    let files = [
      { id: "f1", ref_type: "project", ref_id: "p1", original_name: "spec.pdf", mime: "application/pdf", size_bytes: 2048, sha256: "abcdef0123456789", uploaded_by: "u", uploaded_by_name: "Priya PM", created_at: "2026-11-04T10:00:00Z", previewable: true, row_version: 1 },
    ];
    let uploaded = false;
    let deleted = "";
    mockApi(
      base({
        "GET /projects/p1/tree": () => TREE,
        "GET /files": () => files,
        "POST /files": ({ body }) => {
          const fd = body as FormData;
          uploaded = fd.get("ref_type") === "project" && fd.get("ref_id") === "p1" && (fd.get("file") as File).name === "photo.png";
          files = [{ ...files[0]!, id: "f2", original_name: "photo.png", mime: "image/png" }, ...files];
          return files[0];
        },
        "DELETE /files/f1": ({ path }) => {
          deleted = path;
          files = files.filter((f) => f.id !== "f1");
          return new Response(null, { status: 204 });
        },
      }),
    );
    renderAt("/projects/p1?tab=files");
    const list = await screen.findByRole("list", { name: "Project files list" });
    expect(within(list).getByText("spec.pdf")).toBeInTheDocument();
    expect(within(list).getByText(/2\.0 KiB · Priya PM/)).toBeInTheDocument();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["x"], "photo.png", { type: "image/png" }));
    expect(await screen.findByText("1 file attached")).toBeInTheDocument();
    expect(uploaded).toBe(true);
    expect(await within(screen.getByRole("list", { name: "Project files list" })).findByText("photo.png")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete spec.pdf" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Delete file?" })).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleted).toBe("/files/f1?row_version=1"));
    await waitFor(() => expect(screen.queryByText("spec.pdf")).not.toBeInTheDocument());
  });
});

describe("Top bar switchers", () => {
  it("filters the projects list by the chosen division and remembers it", async () => {
    const { calls } = mockApi(base({ "GET /projects": () => ({ items: [project({})], total: 1, page: 1, page_size: 500 }) }));
    renderAt("/projects");
    await screen.findByText("PLC Rack");
    await userEvent.click(screen.getByRole("combobox", { name: "Division" }));
    await userEvent.click(await screen.findByRole("option", { name: "Power" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("division_id=d2"))).toBe(true));
    expect(localStorage.getItem("fabtrack.division")).toBe("d2");
    expect(screen.queryByRole("region", { name: /Industrial/ })).not.toBeInTheDocument();
  });

  it("jumps to a project from the project switcher", async () => {
    mockApi(base({
      "GET /projects": ({ path }) => ({ items: path.includes("q=bms") ? [project({ id: "p3", code: "PRJ-2026-0003", name: "BMS 48V" })] : [], total: 1, page: 1, page_size: 15 }),
      "GET /projects/p3/tree": () => ({ ...TREE, project: project({ id: "p3", code: "PRJ-2026-0003", name: "BMS 48V" }) }),
    }));
    const router = renderAt("/");
    await userEvent.click(await screen.findByRole("combobox", { name: "Jump to project" }));
    await userEvent.type(screen.getByPlaceholderText("Code, name or client"), "bms");
    await userEvent.click(await screen.findByText("PRJ-2026-0003 · BMS 48V"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/p3"));
  });
});

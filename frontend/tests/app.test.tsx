import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { llmIndicator } from "@/app/LlmStatus";
import { ErrorPage } from "@/app/pages";
import { Shell } from "@/app/Shell";
import { RequireAuth } from "@/features/auth/RequireAuth";
import type { HealthResponse } from "@/features/system/api";

import { HEALTH, errorResponse, makeMe, mockApi, renderAt, signedInRoutes } from "./utils";

describe("App shell (signed in)", () => {
  it("renders the shell and the dashboard with live system status", async () => {
    const { calls } = mockApi(signedInRoutes());
    renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    for (const label of ["Dashboard", "Projects", "BOQ", "Procurement", "Inventory", "Production", "QC", "Reports", "Documents", "Design Lab", "Settings"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(await screen.findByText("1.3 ms")).toBeInTheDocument();
    expect(screen.getByText("50.0 GiB / 100.0 GiB")).toBeInTheDocument();
    expect(screen.getByTestId("llm-status")).toHaveAttribute("data-tone", "grey");
    expect(screen.getByRole("button", { name: /Account menu.*Plant Admin/ })).toBeInTheDocument();
    // The access token from /auth/refresh is attached to API calls.
    expect(calls.find((c) => c.path === "/health")?.auth).toBe("Bearer access-1");
  });

  it("shows the API error on the dashboard when the server fails", async () => {
    mockApi(signedInRoutes(undefined, { "GET /health": () => errorResponse(500, "internal_error", "An unexpected error occurred") }));
    renderAt("/");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Cannot reach the FabTrack API")).toBeInTheDocument();
    expect(within(alert).getByText("An unexpected error occurred")).toBeInTheDocument();
  });

  it("unbuilt sections state which phase delivers them", async () => {
    mockApi(signedInRoutes());
    renderAt("/qc");
    expect(await screen.findByRole("heading", { name: "QC is delivered in Phase 8" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "QC" })).toHaveAttribute("aria-current", "page");
  });

  it("Ctrl+K opens the command palette and navigates", async () => {
    mockApi(signedInRoutes());
    const router = renderAt("/");
    await screen.findByRole("heading", { level: 1, name: "Dashboard" });
    await userEvent.keyboard("{Control>}k{/Control}");
    const palette = await screen.findByRole("dialog", { name: "Command palette" });
    await userEvent.type(within(palette).getByRole("combobox"), "design lab");
    await userEvent.keyboard("{Enter}");
    expect(router.state.location.pathname).toBe("/design-lab");
    expect(await screen.findByRole("heading", { name: "Design Lab is delivered in Phase 12" })).toBeInTheDocument();
  });

  it("collapses the sidebar and remembers it", async () => {
    mockApi(signedInRoutes());
    renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem("fabtrack.sidebar-collapsed")).toBe("1");
    const projects = screen.getByRole("link", { name: "Projects" });
    // Regression: links inside Radix tooltip triggers once rendered a stringified function as class.
    expect(projects.className).toContain("justify-center");
    expect(projects.className).not.toContain("isActive");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });

  it("renders the 404 page for unknown routes", async () => {
    mockApi(signedInRoutes());
    renderAt("/no/such/page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute("href", "/");
  });

  it("renders the error boundary page inside the shell when a page crashes", async () => {
    mockApi(signedInRoutes());
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error("Tracker exploded");
    }
    renderAt("/boom", [
      {
        element: <RequireAuth />,
        children: [{ path: "/", element: <Shell />, children: [{ errorElement: <ErrorPage inShell />, children: [{ path: "boom", element: <Boom /> }] }] }],
      },
    ]);
    expect(await screen.findByRole("heading", { name: "Something went wrong on this page" })).toBeInTheDocument();
    expect(screen.getByText("Tracker exploded")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeInTheDocument();
  });
});

describe("Role-aware navigation", () => {
  const viewer = makeMe({ id: "u-v", username: "client", full_name: "Client Viewer", roles: ["viewer"], permissions: ["projects:read", "reports:read_issued"] });

  it("a client viewer sees only Projects and Reports and lands on Projects", async () => {
    mockApi(signedInRoutes(viewer, { "GET /divisions": () => [], "GET /projects": () => ({ items: [], total: 0, page: 1, page_size: 500 }) }));
    const router = renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New project" })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects");
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Projects", "Reports"]);
  });

  it("direct links to forbidden sections show the forbidden page", async () => {
    mockApi(signedInRoutes(viewer));
    const router = renderAt("/settings/users");
    expect(await screen.findByRole("heading", { name: "You do not have access to this page" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/forbidden");
  });
});

describe("LLM status indicator", () => {
  it("maps provider status to green / blue / grey", () => {
    const healthy = HEALTH as HealthResponse;
    expect(llmIndicator(undefined).tone).toBe("grey");
    expect(llmIndicator(healthy).tone).toBe("grey");
    expect(llmIndicator({ ...healthy, llm: { status: "ok", provider: "lmstudio", detail: "qwen loaded" } })).toMatchObject({ tone: "green", label: "AI local" });
    expect(llmIndicator({ ...healthy, llm: { status: "ok", provider: "openrouter", detail: "online" } })).toMatchObject({ tone: "blue", label: "AI online" });
    expect(llmIndicator({ ...healthy, llm: { status: "error", provider: "lmstudio", detail: "LM Studio not running" } }).tone).toBe("grey");
  });
});

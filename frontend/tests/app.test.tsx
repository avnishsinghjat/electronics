import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import { llmIndicator } from "@/app/LlmStatus";
import { ErrorPage } from "@/app/pages";
import { routes } from "@/app/router";
import { TooltipProvider } from "@/design/components";
import type { HealthResponse } from "@/features/system/api";

import { jsonResponse } from "./utils";

const healthy: HealthResponse = {
  status: "ok",
  version: "0.0.1",
  environment: "test",
  air_gapped: true,
  database: { status: "ok", latency_ms: 1.25, detail: null },
  disk: { status: "ok", path: "/srv/data", free_bytes: 50 * 1024 ** 3, total_bytes: 100 * 1024 ** 3, detail: null },
  llm: { status: "not_configured", provider: null, detail: "LLM gateway not configured (delivered in Phase 9)" },
};

function renderAt(path: string, extraRoutes = routes) {
  const router = createMemoryRouter(extraRoutes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return router;
}

describe("App root", () => {
  it("renders the shell and the dashboard with live system status", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy)));
    vi.stubGlobal("fetch", fetchMock);
    render(<App queryClient={new QueryClient({ defaultOptions: { queries: { retry: false } } })} />);

    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    for (const label of ["Dashboard", "Projects", "BOQ", "Procurement", "Inventory", "Production", "QC", "Reports", "Documents", "Design Lab", "Settings"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(await screen.findByText("1.3 ms")).toBeInTheDocument();
    expect(screen.getByText("50.0 GiB / 100.0 GiB")).toBeInTheDocument();
    expect(screen.getByTestId("llm-status")).toHaveAttribute("data-tone", "grey");
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("shows the API error on the dashboard when the server fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred", details: null } }, 500)),
      ),
    );
    renderAt("/");
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Cannot reach the FabTrack API")).toBeInTheDocument();
    expect(within(alert).getByText("An unexpected error occurred")).toBeInTheDocument();
  });
});

describe("Navigation", () => {
  it("unbuilt sections state which phase delivers them", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy))));
    renderAt("/procurement");
    expect(await screen.findByRole("heading", { name: "Procurement is delivered in Phase 6" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Procurement" })).toHaveAttribute("aria-current", "page");
  });

  it("Ctrl+K opens the command palette and navigates", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy))));
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
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy))));
    renderAt("/");
    await userEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem("fabtrack.sidebar-collapsed")).toBe("1");
    const projects = screen.getByRole("link", { name: "Projects" }); // label kept for screen readers
    // Regression: links inside Radix tooltip triggers once rendered a stringified function as class.
    expect(projects.className).toContain("justify-center");
    expect(projects.className).not.toContain("isActive");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  });

  it("renders the 404 page for unknown routes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy))));
    renderAt("/no/such/page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute("href", "/");
  });

  it("renders the error boundary page inside the shell when a page crashes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy))));
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error("Tracker exploded");
    }
    const root = routes[0]!;
    renderAt("/boom", [
      {
        path: "/",
        element: root.element,
        children: [{ errorElement: <ErrorPage inShell />, children: [{ path: "boom", element: <Boom /> }] }],
      },
    ]);
    expect(await screen.findByRole("heading", { name: "Something went wrong on this page" })).toBeInTheDocument();
    expect(screen.getByText("Tracker exploded")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeInTheDocument();
  });
});

describe("LLM status indicator", () => {
  it("maps provider status to green / blue / grey", () => {
    expect(llmIndicator(undefined).tone).toBe("grey");
    expect(llmIndicator(healthy).tone).toBe("grey");
    expect(llmIndicator({ ...healthy, llm: { status: "ok", provider: "lmstudio", detail: "qwen loaded" } })).toMatchObject({ tone: "green", label: "AI local" });
    expect(llmIndicator({ ...healthy, llm: { status: "ok", provider: "openrouter", detail: "online" } })).toMatchObject({ tone: "blue", label: "AI online" });
    expect(llmIndicator({ ...healthy, llm: { status: "error", provider: "lmstudio", detail: "LM Studio not running" } }).tone).toBe("grey");
  });
});

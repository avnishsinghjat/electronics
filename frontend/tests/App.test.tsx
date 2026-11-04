import { QueryClient } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/App";
import type { HealthResponse } from "@/features/system/api";

const healthy: HealthResponse = {
  status: "ok",
  version: "0.0.1",
  environment: "test",
  air_gapped: true,
  database: { status: "ok", latency_ms: 1.25, detail: null },
  disk: {
    status: "ok",
    path: "/srv/data",
    free_bytes: 50 * 1024 ** 3,
    total_bytes: 100 * 1024 ** 3,
    detail: null,
  },
  llm: {
    status: "not_configured",
    provider: null,
    detail: "LLM gateway not configured (delivered in Phase 9)",
  },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<App queryClient={client} />);
}

describe("App root", () => {
  it("renders the app root with a loading state, then system status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(healthy));
    vi.stubGlobal("fetch", fetchMock);

    renderApp();

    expect(screen.getByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading system status" })).toBeInTheDocument();

    expect(await screen.findByText("0.0.1")).toBeInTheDocument();
    expect(screen.getByText("1.3 ms")).toBeInTheDocument();
    expect(screen.getByText("50.0 GiB / 100.0 GiB")).toBeInTheDocument();
    expect(screen.getByText("LLM gateway not configured (delivered in Phase 9)")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("shows the API error message when the server returns the standard error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "internal_error", message: "An unexpected error occurred", details: null } },
          500,
        ),
      ),
    );

    renderApp();

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Cannot reach the FabTrack API")).toBeInTheDocument();
    expect(within(alert).getByText("An unexpected error occurred")).toBeInTheDocument();
  });

  it("shows a network error when the server is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderApp();
    expect(await screen.findByText("The FabTrack server could not be reached")).toBeInTheDocument();
  });

  it("refresh button refetches health", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(healthy)));
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await screen.findByText("0.0.1");

    await userEvent.click(screen.getByRole("button", { name: "Refresh system status" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});

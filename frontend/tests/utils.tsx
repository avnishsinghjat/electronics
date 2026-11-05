import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type * as React from "react";
import { MemoryRouter, RouterProvider, createMemoryRouter, type RouteObject } from "react-router-dom";

import { routes } from "@/app/router";
import { AuthProvider } from "@/features/auth/AuthContext";

import { Toaster, TooltipProvider } from "@/design/components";

export function renderUi(ui: React.ReactElement, { route = "/" }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={0}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/* ------------------------------------------------------------------ fake API server */

import { vi } from "vitest";

import type { Me, TokenResponse } from "@/features/auth/types";

export type Handler = (req: { method: string; path: string; body: unknown; headers: Headers }) => unknown | Response | Promise<unknown | Response>;

/** Routes fetch("/api/...") calls to handlers keyed by "METHOD /path" (path without query).
 *  Returns the mock so tests can assert on calls. Unknown routes return a 404 error body. */
export function mockApi(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown; auth: string | null }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api/, "");
    const headers = new Headers(init?.headers);
    let body: unknown = undefined;
    if (typeof init?.body === "string") body = JSON.parse(init.body);
    else if (init?.body instanceof FormData) body = init.body;
    calls.push({ method, path: path + url.search, body, auth: headers.get("authorization") });
    const handler = routes[`${method} ${path}`];
    if (!handler) return jsonResponse({ error: { code: "not_found", message: `No mock for ${method} ${path}`, details: null } }, 404);
    const result = await handler({ method, path: path + url.search, body, headers });
    return result instanceof Response ? result : jsonResponse(result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export function errorResponse(status: number, code: string, message: string): Response {
  return jsonResponse({ error: { code, message, details: null } }, status);
}

export const ALL_PERMISSIONS = [
  "users:read", "users:manage", "audit:read", "settings:read", "settings:manage", "divisions:read", "divisions:manage",
  "projects:read", "projects:manage", "files:upload", "files:delete", "boq:read", "boq:edit", "boq:import", "boq:release",
  "parts:read", "parts:manage", "procurement:read", "vendors:manage", "pr:create", "pr:approve", "po:manage", "grn:create",
  "inventory:read", "inventory:transfer", "inventory:adjust", "inventory:approve_adjustment", "production:read", "wo:manage",
  "wo:release", "wo:override_release", "kitting:issue", "stage:progress", "qc:read", "qc:inspect", "qc:manage_templates",
  "ncr:raise", "ncr:close", "reports:read", "reports:read_issued", "reports:create", "reports:review", "reports:approve",
  "documents:read", "documents:draft", "documents:approve", "design:read", "design:run", "design:signoff", "llm:use",
  "llm:manage", "dashboard:read",
];

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: "u-admin",
    username: "admin",
    full_name: "Plant Admin",
    email: null,
    roles: ["admin"],
    permissions: ALL_PERMISSIONS,
    scopes: [],
    must_change_password: false,
    ...overrides,
  };
}

export function token(user: Me = makeMe(), access = "access-1"): TokenResponse {
  return { access_token: access, token_type: "bearer", expires_at: "2099-01-01T00:00:00Z", user };
}

export const HEALTH = {
  status: "ok",
  version: "0.0.1",
  environment: "test",
  air_gapped: true,
  database: { status: "ok", latency_ms: 1.25, detail: null },
  disk: { status: "ok", path: "/srv/data", free_bytes: 50 * 1024 ** 3, total_bytes: 100 * 1024 ** 3, detail: null },
  llm: { status: "not_configured", provider: null, detail: "LLM gateway not configured (delivered in Phase 9)" },
};

export const READY = { needs_setup: false, data_dir: { path: "/srv/data", exists: true, writable: true, free_bytes: 5e10, ok: true, detail: null }, numbering: [] };
export const BRANDING = { company_name: "Sahyadri Electronics", has_logo: false, logo_url: null, setup_complete: true };

/** Default backend for a signed-in admin. */
export function signedInRoutes(user: Me = makeMe(), extra: Record<string, Handler> = {}): Record<string, Handler> {
  return {
    "GET /setup/status": () => READY,
    "POST /auth/refresh": () => token(user),
    "GET /health": () => HEALTH,
    "GET /settings/branding": () => BRANDING,
    "POST /auth/logout": () => new Response(null, { status: 204 }),
    ...extra,
  };
}

/** Renders the real route table (with AuthProvider) at a path; returns the router. */
export function renderAt(path: string, routeTable: RouteObject[] = routes) {
  const router = createMemoryRouter(routeTable, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <TooltipProvider>
          <RouterProvider router={router} />
          <Toaster />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
  return router;
}

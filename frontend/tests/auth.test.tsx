import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { safeNext } from "@/features/auth/LoginPage";
import { apiGet, setAccessToken } from "@/lib/api";

import { BRANDING, HEALTH, READY, errorResponse, makeMe, mockApi, renderAt, signedInRoutes, token } from "./utils";

const anonymous = {
  "GET /setup/status": () => READY,
  "POST /auth/refresh": () => errorResponse(401, "no_session", "Not signed in"),
  "GET /settings/branding": () => BRANDING,
  "GET /health": () => HEALTH,
};

describe("Sign in", () => {
  it("redirects anonymous users to the login page, keeping the destination", async () => {
    mockApi(anonymous);
    const router = renderAt("/settings/users");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("?next=%2Fsettings%2Fusers");
    expect(await screen.findByText("Sahyadri Electronics")).toBeInTheDocument();
  });

  it("validates, shows server errors and signs in to the requested page", async () => {
    let attempts = 0;
    const { calls } = mockApi({
      ...anonymous,
      "POST /auth/login": ({ body }) => {
        attempts += 1;
        const { password } = body as { password: string };
        if (password !== "Right-pass-2026") return errorResponse(401, "invalid_credentials", "Invalid username or password");
        return token(makeMe());
      },
      "GET /users": () => ({ items: [], total: 0, page: 1, page_size: 500 }),
      "GET /users/roles": () => [],
    });
    const router = renderAt("/login?next=%2Fsettings%2Fusers");
    await screen.findByRole("heading", { name: "Sign in" });
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your username")).toBeInTheDocument();
    expect(attempts).toBe(0);

    await userEvent.type(screen.getByLabelText("Username"), "admin");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-pass-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(screen.getByLabelText("Password")).toHaveValue("");

    await userEvent.type(screen.getByLabelText("Password"), "Right-pass-2026");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/settings/users"));
    expect(calls.find((c) => c.path === "/auth/login")?.auth).toBeNull();
  });

  it("shows the lockout message", async () => {
    mockApi({ ...anonymous, "POST /auth/login": () => errorResponse(423, "account_locked", "Account locked for 15 minutes after 5 failed attempts.") });
    renderAt("/login");
    await userEvent.type(await screen.findByLabelText("Username"), "arjun");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Account locked for 15 minutes");
  });

  it("only redirects within the app after sign-in", () => {
    expect(safeNext("/qc")).toBe("/qc");
    expect(safeNext("//evil.example/")).toBe("/");
    expect(safeNext("https://evil.example/")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});

describe("Forced password change", () => {
  it("sends users with a temporary password to the change page and then in", async () => {
    const must = makeMe({ must_change_password: true, username: "priya", full_name: "Priya PM" });
    mockApi(
      signedInRoutes(must, {
        "POST /auth/change-password": ({ body }) => {
          const b = body as { current_password: string; new_password: string };
          if (b.current_password !== "TEMP-1234-abcd") return errorResponse(422, "wrong_password", "Current password is incorrect");
          return token(makeMe({ username: "priya", full_name: "Priya PM" }), "access-2");
        },
      }),
    );
    const router = renderAt("/");
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/change-password");

    await userEvent.type(screen.getByLabelText("Temporary password"), "wrong");
    await userEvent.type(screen.getByLabelText("New password"), "short");
    await userEvent.type(screen.getByLabelText("Confirm new password"), "other");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(screen.getByText("At least 10 characters")).toBeInTheDocument();
    expect(screen.getByText("Passwords do not match")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("New password"));
    await userEvent.type(screen.getByLabelText("New password"), "Fresh-new-pass-77");
    await userEvent.clear(screen.getByLabelText("Confirm new password"));
    await userEvent.type(screen.getByLabelText("Confirm new password"), "Fresh-new-pass-77");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("Current password is incorrect")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("Temporary password"));
    await userEvent.type(screen.getByLabelText("Temporary password"), "TEMP-1234-abcd");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });
});

describe("Sessions", () => {
  it("renews an expired access token once and retries the request", async () => {
    let refreshes = 0;
    const { calls } = mockApi({
      "POST /auth/refresh": () => {
        refreshes += 1;
        return token(makeMe(), `access-${refreshes + 1}`);
      },
      "GET /health": ({ headers }) =>
        headers.get("authorization") === "Bearer access-2" ? HEALTH : errorResponse(401, "token_expired", "Session expired"),
    });
    const { setRefreshHandler } = await import("@/lib/api");
    setAccessToken("access-1");
    setRefreshHandler(async () => {
      const r = await fetch("/api/auth/refresh", { method: "POST" });
      const t = (await r.json()) as { access_token: string };
      setAccessToken(t.access_token);
      return t.access_token;
    });
    const [a, b] = await Promise.all([apiGet<typeof HEALTH>("/health"), apiGet<typeof HEALTH>("/health")]);
    expect(a.status).toBe("ok");
    expect(b.status).toBe("ok");
    expect(refreshes).toBe(1); // single-flight
    expect(calls.filter((c) => c.path === "/health").map((c) => c.auth)).toEqual(["Bearer access-1", "Bearer access-1", "Bearer access-2", "Bearer access-2"]);
    setRefreshHandler(null);
    setAccessToken(null);
  });

  it("signs out to the login page with a notice when the session cannot be renewed", async () => {
    let refreshCalls = 0;
    mockApi({
      ...anonymous,
      "POST /auth/refresh": () => {
        refreshCalls += 1;
        return refreshCalls === 1 ? token(makeMe()) : errorResponse(401, "session_revoked", "Session ended");
      },
      "GET /health": () => errorResponse(401, "session_revoked", "Session ended, please sign in again"),
    });
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Your session ended. Please sign in again.");
  });

  it("signs out from the user menu", async () => {
    const { calls } = mockApi(signedInRoutes());
    const router = renderAt("/");
    await userEvent.click(await screen.findByRole("button", { name: /Account menu.*Plant Admin/ }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Admin")).toBeInTheDocument();
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(calls.some((c) => c.method === "POST" && c.path === "/auth/logout")).toBe(true);
  });
});

describe("First-run setup wizard", () => {
  it("walks through data check, admin, prefixes and logo", async () => {
    let setupBody: unknown = null;
    mockApi({
      "GET /setup/status": () => ({
        ...READY,
        needs_setup: true,
        numbering: [
          { doc_type: "PO", description: "Purchase order", prefix: "PO", padding: 4, yearly_reset: true, example: "PO-2026-0001" },
          { doc_type: "GRN", description: "Goods receipt note", prefix: "GRN", padding: 4, yearly_reset: true, example: "GRN-2026-0001" },
        ],
      }),
      "GET /settings/branding": () => ({ ...BRANDING, company_name: null, setup_complete: false }),
      "POST /setup": ({ body }) => {
        setupBody = body;
        return token(makeMe({ full_name: "Plant Admin" }));
      },
      "GET /health": () => HEALTH,
    });
    const router = renderAt("/");
    expect(await screen.findByRole("heading", { name: "Set up FabTrack" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/setup");
    expect(await screen.findByText("Data directory is ready")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Continue/ }));

    await userEvent.type(screen.getByLabelText(/Company name/), "Sahyadri Electronics");
    await userEvent.type(screen.getByLabelText(/Administrator full name/), "Plant Admin");
    await userEvent.type(screen.getByLabelText(/^Password/), "Setup-pass-2026");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "Setup-pass-2026");
    await userEvent.click(screen.getByRole("button", { name: /Continue/ }));

    const po = await screen.findByLabelText("Purchase order");
    await userEvent.clear(po);
    await userEvent.type(po, "pur");
    expect(po).toHaveValue("PUR");
    await userEvent.click(screen.getByRole("button", { name: "Create company and administrator" }));

    expect(await screen.findByText(/Setup is complete and you are signed in/)).toBeInTheDocument();
    expect(setupBody).toEqual({
      company_name: "Sahyadri Electronics",
      admin: { username: "admin", full_name: "Plant Admin", password: "Setup-pass-2026" },
      prefixes: { PO: "PUR" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Skip for now" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
  });

  it("blocks continuing when the data directory is not usable", async () => {
    mockApi({
      "GET /setup/status": () => ({ needs_setup: true, numbering: [], data_dir: { path: "/mnt/nas/fabtrack", exists: false, writable: false, free_bytes: null, ok: false, detail: "Directory does not exist" } }),
      "GET /settings/branding": () => BRANDING,
    });
    renderAt("/setup");
    expect(await screen.findByText("Data directory needs attention")).toBeInTheDocument();
    expect(screen.getByText("Directory does not exist")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AuditDiff } from "@/features/settings/AuditLogPage";
import type { AuditEntry, UserRow } from "@/features/settings/api";

import { makeMe, mockApi, renderAt, renderUi, signedInRoutes } from "./utils";

const ROLES = [
  { role: "admin", label: "Admin", permissions: ["users:manage"] },
  { role: "stores", label: "Stores", permissions: ["grn:create"] },
  { role: "viewer", label: "Viewer (client)", permissions: ["projects:read"] },
];

function userRow(p: Partial<UserRow>): UserRow {
  return {
    id: "u1", username: "kavya.stores", full_name: "Kavya", email: null, is_active: true, must_change_password: false,
    locked_until: null, last_login_at: "2026-11-04T10:00:00Z", roles: ["stores"], scopes: [], row_version: 3,
    created_at: "2026-11-01T00:00:00Z", ...p,
  };
}

describe("Users admin", () => {
  it("lists users with status and creates a user, showing the temporary password once", async () => {
    let created: unknown = null;
    mockApi(
      signedInRoutes(makeMe(), {
        "GET /users": () => ({
          items: [userRow({}), userRow({ id: "u2", username: "ravi", full_name: "Ravi", must_change_password: true, roles: ["viewer"] }), userRow({ id: "u3", username: "old", full_name: "Old Timer", is_active: false })],
          total: 3, page: 1, page_size: 500,
        }),
        "GET /users/roles": () => ROLES,
        "GET /divisions": () => [{ id: "d1", code: "IND", name: "Industrial" }],
        "POST /users": ({ body }) => {
          created = body;
          return { user: userRow({ id: "u9", username: "meena", full_name: "Meena", roles: ["stores"], must_change_password: true }), temporary_password: "AbCd-EfGh-JkMn-PqRs" };
        },
      }),
    );
    renderAt("/settings/users");
    expect(await screen.findByText("kavya.stores")).toBeInTheDocument();
    expect(screen.getByText("Must change password")).toBeInTheDocument();
    expect(screen.getByText("Deactivated")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "New user" }));
    const drawer = await screen.findByRole("dialog", { name: "New user" });
    await userEvent.click(within(drawer).getByRole("button", { name: "Create user" }));
    expect(await within(drawer).findByText("Pick at least one role")).toBeInTheDocument();
    await userEvent.type(within(drawer).getByLabelText(/Username/), "meena");
    await userEvent.type(within(drawer).getByLabelText(/Full name/), "Meena");
    await userEvent.click(within(drawer).getByRole("checkbox", { name: /Stores/ }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Create user" }));

    const dlg = await screen.findByRole("dialog", { name: "Temporary password" });
    expect(within(dlg).getByTestId("temporary-password")).toHaveTextContent("AbCd-EfGh-JkMn-PqRs");
    expect(created).toEqual({ username: "meena", full_name: "Meena", email: null, roles: ["stores"], scopes: [] });
  });

  it("resets a password after confirmation and sends the row version", async () => {
    let resetBody: unknown = null;
    mockApi(
      signedInRoutes(makeMe(), {
        "GET /users": () => ({ items: [userRow({})], total: 1, page: 1, page_size: 500 }),
        "GET /users/roles": () => ROLES,
        "POST /users/u1/reset-password": ({ body }) => {
          resetBody = body;
          return { user: userRow({ must_change_password: true }), temporary_password: "Temp-Temp-Temp-Temp" };
        },
      }),
    );
    renderAt("/settings/users");
    await userEvent.click(await screen.findByRole("button", { name: "Reset password for kavya.stores" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Reset password?" })).getByRole("button", { name: "Reset password" }));
    expect(await screen.findByTestId("temporary-password")).toHaveTextContent("Temp-Temp-Temp-Temp");
    expect(resetBody).toEqual({ row_version: 3 });
  });

  it("hides management actions from users who can only read", async () => {
    const pm = makeMe({ roles: ["project_manager"], permissions: ["users:read", "settings:read", "dashboard:read", "projects:read"] });
    mockApi(signedInRoutes(pm, { "GET /users": () => ({ items: [userRow({})], total: 1, page: 1, page_size: 500 }), "GET /users/roles": () => ROLES }));
    renderAt("/settings/users");
    expect(await screen.findByText("kavya.stores")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New user" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reset password for/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });
});

describe("General settings", () => {
  it("saves company details and a document prefix", async () => {
    let companyBody: unknown = null;
    let prefixBody: unknown = null;
    mockApi(
      signedInRoutes(makeMe(), {
        "GET /settings/company": () => ({ company_name: "Old Co", address: null, gstin: null, has_logo: false, row_version: 4 }),
        "PUT /settings/company": ({ body }) => {
          companyBody = body;
          return { company_name: "New Co", address: null, gstin: "27AABCS1234F1Z5", has_logo: false, row_version: 5 };
        },
        "GET /settings/numbering": () => [{ doc_type: "PO", description: "Purchase order", prefix: "PO", padding: 4, yearly_reset: true, example: "PO-2026-0001" }],
        "PUT /settings/numbering/PO": ({ body }) => {
          prefixBody = body;
          return { doc_type: "PO", description: "Purchase order", prefix: "PUR", padding: 4, yearly_reset: true, example: "PUR-2026-0001" };
        },
      }),
    );
    renderAt("/settings/general");
    const name = await screen.findByLabelText(/Company name/);
    await waitFor(() => expect(name).toHaveValue("Old Co"));
    await userEvent.clear(name);
    await userEvent.type(name, "New Co");
    await userEvent.type(screen.getByLabelText(/GSTIN/), "bad");
    await userEvent.click(screen.getByRole("button", { name: /Save company details/ }));
    expect(await screen.findByText("Not a valid 15-character GSTIN")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/GSTIN/));
    await userEvent.type(screen.getByLabelText(/GSTIN/), "27aabcs1234f1z5");
    await userEvent.click(screen.getByRole("button", { name: /Save company details/ }));
    await waitFor(() => expect(companyBody).toEqual({ row_version: 4, company_name: "New Co", address: null, gstin: "27AABCS1234F1Z5" }));

    const prefix = screen.getByLabelText("Prefix for Purchase order");
    await userEvent.clear(prefix);
    await userEvent.type(prefix, "pur");
    expect(screen.getByText("PUR-2026-0001")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(prefixBody).toEqual({ prefix: "PUR" }));
  });
});

describe("Audit log", () => {
  const entry: AuditEntry = {
    id: 7, occurred_at: "2026-11-04T10:00:00Z", actor_id: "u1", actor_username: "editor", actor_name: "Editor",
    action: "update", entity_type: "divisions", entity_id: "d1",
    before: { name: "Before", code: "IND", row_version: 1 }, after: { name: "After", code: "IND", row_version: 2 },
    changed_fields: ["name"], request_id: "req-1",
  };

  it("diff view highlights changed fields first and hides bookkeeping columns", () => {
    renderUi(<AuditDiff entry={entry} />);
    const rows = within(screen.getByRole("table", { name: "Field changes" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual(["name", "code"]);
    expect(rows[0]).toHaveAttribute("data-changed", "true");
    expect(within(rows[0]!).getByText("Before")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("After")).toBeInTheDocument();
  });

  it("filters by record type and pages through results", async () => {
    const { calls } = mockApi(
      signedInRoutes(makeMe(), {
        "GET /users": () => ({ items: [], total: 0, page: 1, page_size: 500 }),
        "GET /audit/entity-types": () => ["divisions", "users"],
        "GET /audit": () => ({ items: [entry], total: 150, page: 1, page_size: 100 }),
      }),
    );
    renderAt("/settings/audit");
    expect(await screen.findByText("150 entries · page 1 of 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "View change 7" }));
    expect(await screen.findByRole("dialog", { name: "Updated: divisions" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(calls.some((c) => c.path.startsWith("/audit?") && c.path.includes("page=2"))).toBe(true));
    await userEvent.click(screen.getByRole("combobox", { name: "Record type" }));
    await userEvent.click(await screen.findByRole("option", { name: "users" }));
    await waitFor(() => expect(calls.some((c) => c.path.includes("entity_type=users") && c.path.includes("page=1"))).toBe(true));
  });
});

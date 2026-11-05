import { zodResolver } from "@hookform/resolvers/zod";
import type { ColumnDef } from "@tanstack/react-table";
import { Copy, KeyRound, Plus, UserCheck, UserX, Users, X } from "lucide-react";
import * as React from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import {
  Badge,
  Button,
  Checkbox,
  Combobox,
  type ComboboxOption,
  DataTable,
  Dialog,
  DialogContent,
  Drawer,
  DrawerContent,
  EmptyState,
  Field,
  Input,
  Label,
  MonoText,
  StatusPill,
  toast,
} from "@/design/components";
import { useAuth } from "@/features/auth/AuthContext";
import { ROLE_LABELS, type Role, type Scope } from "@/features/auth/types";
import { ApiError } from "@/lib/api";

import { type UserRow, type UserWithPassword, searchProjects, useDivisions, useRoles, useUserMutations, useUsers } from "./api";

const userSchema = z.object({
  username: z.string().trim().regex(/^[A-Za-z0-9._-]{3,64}$/, "3-64 letters, digits, dot, dash or underscore"),
  full_name: z.string().trim().min(1, "Enter the full name").max(200),
  email: z.union([z.literal(""), z.string().email("Not a valid email address")]),
  roles: z.array(z.string()).min(1, "Pick at least one role"),
});
type UserForm = z.infer<typeof userSchema>;

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Never";
}

function userStatus(u: UserRow): { tone: "green" | "grey" | "amber" | "red"; label: string } {
  if (!u.is_active) return { tone: "grey", label: "Deactivated" };
  if (u.locked_until && new Date(u.locked_until) > new Date()) return { tone: "red", label: "Locked" };
  if (u.must_change_password) return { tone: "amber", label: "Must change password" };
  return { tone: "green", label: "Active" };
}

function TemporaryPasswordDialog({ result, onClose }: { result: UserWithPassword | null; onClose: () => void }) {
  return (
    <Dialog open={result !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title="Temporary password"
        description="Shown once. Give it to the user in person; they must choose their own password when they sign in."
        footer={<Button onClick={onClose}>Done</Button>}
      >
        {result && (
          <div className="space-y-3">
            <p className="text-sm text-neutral-600">
              User <MonoText>{result.user.username}</MonoText>
            </p>
            <div className="flex items-center gap-2 rounded-md border bg-neutral-50 px-3 py-2">
              <MonoText className="flex-1 select-all text-md" data-testid="temporary-password">
                {result.temporary_password}
              </MonoText>
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Copy password"
                onClick={() =>
                  void navigator.clipboard
                    ?.writeText(result.temporary_password)
                    .then(() => toast.success("Copied"))
                    .catch(() => toast.error("Copy is blocked by this browser; select the text instead"))
                }
              >
                <Copy />
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ScopeEditor({ scopes, onChange }: { scopes: Scope[]; onChange: (s: Scope[]) => void }) {
  const divisions = useDivisions();
  const [projectNames, setProjectNames] = React.useState<Record<string, string>>({});
  const divisionName = (id: string) => divisions.data?.find((d) => d.id === id)?.name ?? id;
  const loadProjects = React.useCallback(async (q: string, signal: AbortSignal): Promise<ComboboxOption[]> => {
    const rows = await searchProjects(q, signal);
    setProjectNames((m) => ({ ...m, ...Object.fromEntries(rows.map((r) => [r.id, `${r.code} · ${r.name}`])) }));
    return rows.map((r) => ({ value: r.id, label: `${r.code} · ${r.name}`, description: r.client_name }));
  }, []);
  const loadDivisions = React.useCallback(
    async (q: string): Promise<ComboboxOption[]> =>
      (divisions.data ?? [])
        .filter((d) => !q || `${d.code} ${d.name}`.toLowerCase().includes(q.toLowerCase()))
        .map((d) => ({ value: d.id, label: d.name, description: d.code })),
    [divisions.data],
  );
  const add = (scope_type: Scope["scope_type"], opt: ComboboxOption | null) => {
    if (!opt || scopes.some((s) => s.scope_id === opt.value)) return;
    if (scope_type === "project") setProjectNames((m) => ({ ...m, [opt.value]: opt.label }));
    onChange([...scopes, { scope_type, scope_id: opt.value }]);
  };
  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-500">No scope means the user sees every division and project their roles allow. Admins are never restricted.</p>
      {scopes.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Current scopes">
          {scopes.map((s) => (
            <li key={s.scope_id}>
              <Badge tone="outline" className="gap-1.5 py-0.5">
                <span className="text-neutral-500">{s.scope_type === "division" ? "Division" : "Project"}:</span>
                {s.scope_type === "division" ? divisionName(s.scope_id) : (projectNames[s.scope_id] ?? s.scope_id)}
                <button type="button" aria-label="Remove scope" className="rounded text-neutral-500 hover:text-neutral-900" onClick={() => onChange(scopes.filter((x) => x.scope_id !== s.scope_id))}>
                  <X className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <Combobox aria-label="Add division scope" value={null} onChange={(o) => add("division", o)} loadOptions={loadDivisions} placeholder="Add a division…" />
        <Combobox aria-label="Add project scope" value={null} onChange={(o) => add("project", o)} loadOptions={loadProjects} placeholder="Add a project…" />
      </div>
    </div>
  );
}

function UserDrawer({ open, user, onClose, onCreated }: {
  open: boolean;
  user: UserRow | null;
  onClose: () => void;
  onCreated: (r: UserWithPassword) => void;
}) {
  const roles = useRoles();
  const { create, update } = useUserMutations();
  const [scopes, setScopes] = React.useState<Scope[]>(user?.scopes ?? []);
  const [error, setError] = React.useState<string | null>(null);
  const form = useForm<UserForm>({
    resolver: zodResolver(userSchema),
    values: { username: user?.username ?? "", full_name: user?.full_name ?? "", email: user?.email ?? "", roles: user?.roles ?? [] },
  });
  const [lastUser, setLastUser] = React.useState(user);
  if (user !== lastUser) {
    setLastUser(user);
    setScopes(user?.scopes ?? []);
    setError(null);
  }

  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    const payload = { full_name: v.full_name, email: v.email || null, roles: v.roles as Role[], scopes };
    try {
      if (user) {
        await update.mutateAsync({ id: user.id, row_version: user.row_version, ...payload });
        toast.success(`${v.full_name} updated`);
      } else {
        const created = await create.mutateAsync({ username: v.username, ...payload });
        onCreated(created);
      }
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
    }
  });

  return (
    <Drawer open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerContent
        width="560px"
        title={user ? `Edit ${user.full_name}` : "New user"}
        description={user ? undefined : "FabTrack creates a temporary password; the user picks their own at first sign-in."}
        footer={
          <>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={() => void onSubmit()} loading={form.formState.isSubmitting}>
              {user ? "Save changes" : "Create user"}
            </Button>
          </>
        }
      >
        <form onSubmit={onSubmit} noValidate className="space-y-5">
          {error && (
            <p role="alert" className="rounded-md border border-status-red-border bg-status-red-bg px-3 py-2 text-sm text-status-red-fg">
              {error}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Username" htmlFor="u-username" error={form.formState.errors.username?.message} required>
              <Input disabled={user !== null} autoCapitalize="none" className="font-mono" {...form.register("username")} />
            </Field>
            <Field label="Full name" htmlFor="u-full_name" error={form.formState.errors.full_name?.message} required>
              <Input {...form.register("full_name")} />
            </Field>
            <Field label="Email" htmlFor="u-email" className="sm:col-span-2" hint="Optional; used for LAN mail notifications if configured" error={form.formState.errors.email?.message}>
              <Input type="email" {...form.register("email")} />
            </Field>
          </div>
          <fieldset>
            <legend className="text-sm font-medium text-neutral-700">Roles</legend>
            {form.formState.errors.roles && <p role="alert" className="mt-1 text-xs text-status-red-fg">{form.formState.errors.roles.message}</p>}
            <Controller
              control={form.control}
              name="roles"
              render={({ field }) => (
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {(roles.data ?? []).map((r) => {
                    const id = `role-${r.role}`;
                    const checked = field.value.includes(r.role);
                    return (
                      <div key={r.role} className="flex items-start gap-2 rounded-md border px-3 py-2">
                        <Checkbox
                          id={id}
                          checked={checked}
                          onCheckedChange={(v) => field.onChange(v === true ? [...field.value, r.role] : field.value.filter((x) => x !== r.role))}
                          className="mt-0.5"
                        />
                        <Label htmlFor={id} className="leading-5">
                          {r.label}
                          <span className="block text-xs font-normal text-neutral-500">{r.permissions.length} permissions</span>
                        </Label>
                      </div>
                    );
                  })}
                </div>
              )}
            />
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-neutral-700">Restrict to divisions or projects</legend>
            <ScopeEditor scopes={scopes} onChange={setScopes} />
          </fieldset>
        </form>
      </DrawerContent>
    </Drawer>
  );
}

export default function UsersPage() {
  const { can, user: me } = useAuth();
  const canManage = can("users:manage");
  const users = useUsers();
  const { reset, setActive } = useUserMutations();
  const [editing, setEditing] = React.useState<UserRow | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [password, setPassword] = React.useState<UserWithPassword | null>(null);
  const [confirm, setConfirm] = React.useState<{ kind: "reset" | "deactivate" | "activate"; user: UserRow } | null>(null);

  const columns = React.useMemo<ColumnDef<UserRow, unknown>[]>(
    () => [
      { accessorKey: "username", header: "Username", size: 170, meta: { mono: true } },
      { accessorKey: "full_name", header: "Name", size: 200 },
      {
        id: "roles",
        header: "Roles",
        size: 260,
        accessorFn: (u) => u.roles.map((r) => ROLE_LABELS[r]).join(", "),
        cell: ({ row }) => (
          <span className="flex gap-1 overflow-hidden">
            {row.original.roles.map((r) => (
              <Badge key={r} tone={r === "admin" ? "accent" : "neutral"}>
                {ROLE_LABELS[r]}
              </Badge>
            ))}
          </span>
        ),
      },
      { id: "scope", header: "Scope", size: 120, accessorFn: (u) => (u.scopes.length ? `${u.scopes.length} restriction(s)` : "All") },
      {
        id: "status",
        header: "Status",
        size: 190,
        accessorFn: (u) => userStatus(u).label,
        cell: ({ row }) => {
          const s = userStatus(row.original);
          return <StatusPill tone={s.tone}>{s.label}</StatusPill>;
        },
      },
      { id: "last_login", header: "Last sign-in", size: 180, accessorFn: (u) => fmtDate(u.last_login_at) },
      ...(canManage
        ? [
            {
              id: "actions",
              header: "",
              size: 220,
              enableSorting: false,
              meta: { filter: false, label: "Actions", align: "right" as const },
              cell: ({ row }: { row: { original: UserRow } }) => {
                const u = row.original;
                return (
                  <span className="flex justify-end gap-1">
                    <Button size="sm" variant="ghost" onClick={() => { setEditing(u); setDrawerOpen(true); }}>
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" aria-label={`Reset password for ${u.username}`} onClick={() => setConfirm({ kind: "reset", user: u })}>
                      <KeyRound />
                    </Button>
                    {u.is_active ? (
                      <Button size="sm" variant="ghost" aria-label={`Deactivate ${u.username}`} disabled={u.id === me?.id} onClick={() => setConfirm({ kind: "deactivate", user: u })}>
                        <UserX />
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" aria-label={`Activate ${u.username}`} onClick={() => setConfirm({ kind: "activate", user: u })}>
                        <UserCheck />
                      </Button>
                    )}
                  </span>
                );
              },
            } satisfies ColumnDef<UserRow, unknown>,
          ]
        : []),
    ],
    [canManage, me?.id],
  );

  const runConfirm = async () => {
    if (!confirm) return;
    const { kind, user } = confirm;
    try {
      if (kind === "reset") {
        setPassword(await reset.mutateAsync({ id: user.id, row_version: user.row_version }));
      } else {
        await setActive.mutateAsync({ id: user.id, row_version: user.row_version, active: kind === "activate" });
        toast.success(`${user.full_name} ${kind === "activate" ? "activated" : "deactivated"}`);
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setConfirm(null);
    }
  };

  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-4">
        <p className="text-sm text-neutral-600">People who can sign in to FabTrack, their roles and what they can see.</p>
        {canManage && (
          <Button onClick={() => { setEditing(null); setDrawerOpen(true); }}>
            <Plus /> New user
          </Button>
        )}
      </div>
      <DataTable
        id="users"
        data={users.data?.items ?? []}
        columns={columns}
        getRowId={(u) => u.id}
        loading={users.isPending}
        error={users.isError ? users.error.message : null}
        exportFileName="fabtrack-users"
        emptyState={<EmptyState icon={Users} title="No users" description="Create the first user account." />}
      />
      <UserDrawer open={drawerOpen} user={editing} onClose={() => setDrawerOpen(false)} onCreated={setPassword} />
      <TemporaryPasswordDialog result={password} onClose={() => setPassword(null)} />
      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent
          size="sm"
          title={confirm?.kind === "reset" ? "Reset password?" : confirm?.kind === "deactivate" ? "Deactivate user?" : "Activate user?"}
          description={
            confirm?.kind === "reset"
              ? "Sets a new temporary password, unlocks the account and signs the user out everywhere."
              : confirm?.kind === "deactivate"
                ? "The user is signed out everywhere and can no longer sign in. Their history is kept."
                : "The user can sign in again with their existing password."
          }
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant={confirm?.kind === "deactivate" ? "danger" : "primary"} onClick={() => void runConfirm()} loading={reset.isPending || setActive.isPending}>
                {confirm?.kind === "reset" ? "Reset password" : confirm?.kind === "deactivate" ? "Deactivate" : "Activate"}
              </Button>
            </>
          }
        >
          {confirm && (
            <p className="text-sm text-neutral-700">
              {confirm.user.full_name} (<MonoText>{confirm.user.username}</MonoText>)
            </p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

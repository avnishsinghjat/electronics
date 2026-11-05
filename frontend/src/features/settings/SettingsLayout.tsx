import { Navigate, NavLink, Outlet } from "react-router-dom";

import { PageHeader } from "@/design/components";
import { useAuth } from "@/features/auth/AuthContext";
import { cn } from "@/lib/utils";

export const SETTINGS_SECTIONS = [
  { to: "general", label: "General", permission: "settings:read" },
  { to: "users", label: "Users", permission: "users:read" },
  { to: "audit", label: "Audit log", permission: "audit:read" },
] as const;

export function SettingsIndex() {
  const { can } = useAuth();
  const first = SETTINGS_SECTIONS.find((s) => can(s.permission));
  return <Navigate to={first ? first.to : "/forbidden"} replace />;
}

export default function SettingsLayout() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader breadcrumb={[{ label: "Home", to: "/" }, { label: "Settings" }]} title="Settings" description="Company details, document numbering, users and the audit log." />
      <nav aria-label="Settings sections" className="mb-5 flex gap-1 border-b">
        {SETTINGS_SECTIONS.filter((s) => can(s.permission)).map((s) => (
          <NavLink
            key={s.to}
            to={s.to}
            className={({ isActive }) =>
              cn(
                "-mb-px inline-flex h-9 items-center border-b-2 px-3 text-sm font-medium focus-visible:shadow-focus focus-visible:outline-none",
                isActive ? "border-accent-600 text-accent-700" : "border-transparent text-neutral-600 hover:text-neutral-900",
              )
            }
          >
            {s.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  );
}

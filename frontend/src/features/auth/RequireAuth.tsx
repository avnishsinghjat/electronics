import { Navigate, Outlet, useLocation } from "react-router-dom";

import { Skeleton } from "@/design/components";

import { useAuth } from "./AuthContext";

export function FullPageLoading() {
  return (
    <div className="app-canvas flex min-h-screen items-center justify-center" aria-busy="true" aria-label="Loading FabTrack">
      <div className="w-72 space-y-3">
        <Skeleton className="mx-auto size-10 rounded-lg" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  );
}

/** Guards the app shell: first-run setup, sign-in and forced password change. */
export function RequireAuth() {
  const { status, user, signedOutByUser } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageLoading />;
  if (status === "setup") return <Navigate to="/setup" replace />;
  if (status === "anonymous" || !user) {
    const next = location.pathname + location.search;
    const keep = !signedOutByUser && next !== "/";
    return <Navigate to={`/login${keep ? `?next=${encodeURIComponent(next)}` : ""}`} replace />;
  }
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return <Outlet />;
}

/** Hides a whole route from users without the permission (server enforces as well). */
export function RequirePermission({ permission, children }: { permission: string | string[]; children: React.ReactNode }) {
  const { user } = useAuth();
  const perms = Array.isArray(permission) ? permission : [permission];
  if (!user || !perms.some((p) => user.permissions.includes(p))) return <Navigate to="/forbidden" replace />;
  return <>{children}</>;
}

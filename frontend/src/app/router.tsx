import { lazy } from "react";
import { Navigate, type RouteObject, createBrowserRouter } from "react-router-dom";

import { RequireAuth, RequirePermission } from "@/features/auth/RequireAuth";
import RoadmapPage from "@/features/roadmap/RoadmapPage";
import { SettingsIndex } from "@/features/settings/SettingsLayout";

import { NAV_ITEMS } from "./navigation";
import { ErrorPage, ForbiddenPage, HomeRoute, NotFoundPage } from "./pages";
import { Shell } from "./Shell";

const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const DevUiPage = lazy(() => import("@/features/dev/DevUiPage"));
const LoginPage = lazy(() => import("@/features/auth/LoginPage"));
const ChangePasswordPage = lazy(() => import("@/features/auth/ChangePasswordPage"));
const SetupPage = lazy(() => import("@/features/auth/SetupPage"));
const SettingsLayout = lazy(() => import("@/features/settings/SettingsLayout"));
const GeneralSettingsPage = lazy(() => import("@/features/settings/GeneralSettingsPage"));
const UsersPage = lazy(() => import("@/features/settings/UsersPage"));
const AuditLogPage = lazy(() => import("@/features/settings/AuditLogPage"));

/** Sections whose module is not built yet render the roadmap page. Each phase replaces
 *  its entry with the real lazily-loaded feature route. */
const BUILT = new Set(["dashboard", "settings"]);
const roadmapRoutes: RouteObject[] = NAV_ITEMS.filter((n) => !BUILT.has(n.id)).map((n) => ({
  path: n.to.slice(1),
  element: (
    <RequirePermission permission={n.permissions}>
      <RoadmapPage sectionId={n.id} />
    </RequirePermission>
  ),
}));

export const routes: RouteObject[] = [
  { path: "/login", element: <LoginPage />, errorElement: <ErrorPage /> },
  { path: "/setup", element: <SetupPage />, errorElement: <ErrorPage /> },
  { path: "/change-password", element: <ChangePasswordPage />, errorElement: <ErrorPage /> },
  {
    element: <RequireAuth />,
    errorElement: <ErrorPage />,
    children: [
      {
        path: "/",
        element: <Shell />,
        children: [
          {
            // Errors inside a page render inside the shell, so navigation keeps working.
            errorElement: <ErrorPage inShell />,
            children: [
              { index: true, element: <HomeRoute dashboard={<DashboardPage />} /> },
              ...roadmapRoutes,
              {
                path: "settings",
                element: (
                  <RequirePermission permission={["settings:read", "users:read", "audit:read"]}>
                    <SettingsLayout />
                  </RequirePermission>
                ),
                children: [
                  { index: true, element: <SettingsIndex /> },
                  { path: "general", element: <RequirePermission permission="settings:read"><GeneralSettingsPage /></RequirePermission> },
                  { path: "users", element: <RequirePermission permission="users:read"><UsersPage /></RequirePermission> },
                  { path: "audit", element: <RequirePermission permission="audit:read"><AuditLogPage /></RequirePermission> },
                ],
              },
              { path: "dev/ui", element: <DevUiPage /> },
              { path: "forbidden", element: <ForbiddenPage /> },
              { path: "home", element: <Navigate to="/" replace /> },
              { path: "*", element: <NotFoundPage /> },
            ],
          },
        ],
      },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}

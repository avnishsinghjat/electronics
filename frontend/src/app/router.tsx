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
const ProjectsPage = lazy(() => import("@/features/projects/ProjectsPage"));
const ProjectPage = lazy(() => import("@/features/projects/ProjectPage"));
const BoqListPage = lazy(() => import("@/features/boq/BoqListPage"));
const ProcurementPage = lazy(() => import("@/features/procurement/ProcurementPage"));
const RequisitionPage = lazy(() => import("@/features/procurement/RequisitionPage"));
const PurchaseOrderPage = lazy(() => import("@/features/procurement/PurchaseOrderPage"));
const ReceiptPage = lazy(() => import("@/features/procurement/ReceiptPage"));
const InventoryPage = lazy(() => import("@/features/inventory/InventoryPage"));

/** Sections whose module is not built yet render the roadmap page. Each phase replaces
 *  its entry with the real lazily-loaded feature route. */
const BUILT = new Set(["dashboard", "settings", "projects", "boq", "procurement", "inventory"]);
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
              { path: "projects", element: <RequirePermission permission="projects:read"><ProjectsPage /></RequirePermission> },
              { path: "boq", element: <RequirePermission permission="boq:read"><BoqListPage /></RequirePermission> },
              { path: "projects/:projectId", element: <RequirePermission permission="projects:read"><ProjectPage /></RequirePermission> },
              { path: "procurement", element: <RequirePermission permission="procurement:read"><ProcurementPage /></RequirePermission> },
              { path: "procurement/requisitions/:prId", element: <RequirePermission permission="procurement:read"><RequisitionPage /></RequirePermission> },
              { path: "procurement/orders/:poId", element: <RequirePermission permission="procurement:read"><PurchaseOrderPage /></RequirePermission> },
              { path: "procurement/receipts/:grnId", element: <RequirePermission permission="procurement:read"><ReceiptPage /></RequirePermission> },
              { path: "inventory", element: <RequirePermission permission="inventory:read"><InventoryPage /></RequirePermission> },
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

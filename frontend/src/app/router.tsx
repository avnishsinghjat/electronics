import { lazy } from "react";
import { type RouteObject, createBrowserRouter } from "react-router-dom";

import RoadmapPage from "@/features/roadmap/RoadmapPage";

import { NAV_ITEMS } from "./navigation";
import { ErrorPage, NotFoundPage } from "./pages";
import { Shell } from "./Shell";

const DashboardPage = lazy(() => import("@/features/dashboard/DashboardPage"));
const DevUiPage = lazy(() => import("@/features/dev/DevUiPage"));

/** Sections whose module is not built yet render the roadmap page. Each phase replaces
 *  its entry with the real lazily-loaded feature route. */
const roadmapRoutes: RouteObject[] = NAV_ITEMS.filter((n) => n.id !== "dashboard").map((n) => ({
  path: n.to.slice(1),
  element: <RoadmapPage sectionId={n.id} />,
}));

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Shell />,
    errorElement: <ErrorPage />,
    children: [
      {
        // Errors inside a page render inside the shell, so navigation keeps working.
        errorElement: <ErrorPage inShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          ...roadmapRoutes,
          { path: "dev/ui", element: <DevUiPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export function createRouter() {
  return createBrowserRouter(routes);
}

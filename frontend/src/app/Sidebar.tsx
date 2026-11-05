import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import * as React from "react";
import { Link, useMatch, useResolvedPath } from "react-router-dom";

import { Tooltip } from "@/design/components";
import { cn } from "@/lib/utils";

import { useAuth } from "@/features/auth/AuthContext";

import { type NavItem, visibleNavItems } from "./navigation";

/** A sidebar link with a plain-string className, so it can be a Radix Slot child (Tooltip
 *  trigger) without NavLink's function className being stringified. */
const SidebarLink = React.forwardRef<HTMLAnchorElement, { item: NavItem; collapsed: boolean } & React.HTMLAttributes<HTMLAnchorElement>>(
  ({ item, collapsed, className, ...rest }, ref) => {
    const resolved = useResolvedPath(item.to);
    const isActive = useMatch({ path: resolved.pathname, end: item.to === "/" }) !== null;
    return (
      <Link
        ref={ref}
        to={item.to}
        aria-current={isActive ? "page" : undefined}
        {...rest}
        className={cn(
          "flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors focus-visible:shadow-focus focus-visible:outline-none",
          collapsed && "justify-center px-0",
          isActive ? "bg-white text-accent-700 shadow-xs ring-1 ring-neutral-200" : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900",
          className,
        )}
      >
        <item.icon className="size-4 shrink-0" aria-hidden="true" />
        {collapsed ? <span className="sr-only">{item.label}</span> : item.label}
      </Link>
    );
  },
);
SidebarLink.displayName = "SidebarLink";

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { user } = useAuth();
  const items = visibleNavItems(user?.permissions ?? []);
  return (
    <aside
      data-shell="sidebar"
      aria-label="Sidebar"
      className={cn(
        "sticky top-0 z-sidebar flex h-screen shrink-0 flex-col border-r bg-sidebar transition-[width] duration-200",
        collapsed ? "w-sidebar-collapsed" : "w-sidebar",
      )}
    >
      <div className={cn("flex h-topbar items-center gap-2.5 border-b px-4", collapsed && "justify-center px-0")}>
        <img src="/favicon.svg" alt="" className="size-7 shrink-0" />
        {!collapsed && (
          <div className="leading-tight">
            <p className="text-sm font-semibold tracking-tight text-neutral-900">FabTrack</p>
            <p className="text-2xs text-neutral-500">Manufacturing ERP</p>
          </div>
        )}
      </div>
      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-0.5">
          {items.map((item) => {
            const link = <SidebarLink item={item} collapsed={collapsed} />;
            return (
              <li key={item.id}>
                {collapsed ? (
                  <Tooltip content={item.label} side="right">
                    {link}
                  </Tooltip>
                ) : (
                  link
                )}
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t p-2">
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          className={cn(
            "flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-xs font-medium text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          {!collapsed && "Collapse"}
        </button>
      </div>
    </aside>
  );
}

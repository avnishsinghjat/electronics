import { Search } from "lucide-react";
import * as React from "react";
import { Outlet, ScrollRestoration } from "react-router-dom";

import { Skeleton } from "@/design/components";
import { readPref, writePref } from "@/lib/storage";

import { CommandPalette, useCommandPaletteShortcut } from "./CommandPalette";
import { isEnabled } from "./features";
import { LlmStatus } from "./LlmStatus";
import { DivisionSwitcher, ProjectSwitcher, useShowSwitchers } from "./Switchers";
import { UserMenu } from "./UserMenu";
import { Sidebar } from "./Sidebar";

function PageFallback() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading page">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-8 w-72" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export function Shell() {
  const [collapsed, setCollapsed] = React.useState(() => readPref("sidebar-collapsed") === "1");
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const showSwitchers = useShowSwitchers() && isEnabled("projectSwitcher");
  useCommandPaletteShortcut(setPaletteOpen);

  const toggle = () =>
    setCollapsed((c) => {
      writePref("sidebar-collapsed", c ? "0" : "1");
      return !c;
    });

  return (
    <div className="flex min-h-screen">
      <a href="#main" className="sr-only z-toast rounded bg-white px-3 py-2 text-sm font-medium shadow-md focus:not-sr-only focus:fixed focus:left-2 focus:top-2">
        Skip to content
      </a>
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header data-shell="topbar" className="hairline-accent sticky top-0 z-sticky flex h-topbar items-center gap-3 border-b bg-white/95 px-6 backdrop-blur">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex h-8 w-full max-w-md items-center gap-2 rounded-md border border-neutral-200 bg-neutral-25 px-3 text-sm text-neutral-500 shadow-xs hover:border-neutral-300 hover:bg-white focus-visible:shadow-focus focus-visible:outline-none"
            aria-keyshortcuts="Control+K"
          >
            <Search className="size-4" aria-hidden="true" />
            <span className="flex-1 text-left">Search or jump to…</span>
            <kbd className="rounded border bg-white px-1.5 py-0.5 font-mono text-2xs text-neutral-500">Ctrl K</kbd>
          </button>
          {showSwitchers && (
            <div className="hidden items-center gap-2 lg:flex">
              <DivisionSwitcher />
              <ProjectSwitcher />
            </div>
          )}
          <div className="ml-auto flex items-center gap-2">
            <LlmStatus />
            {isEnabled("auth") && <UserMenu />}
          </div>
        </header>
        <main id="main" className="app-canvas flex-1 px-6 py-6">
          <div className="mx-auto w-full max-w-[1600px]">
            <React.Suspense fallback={<PageFallback />}>
              <Outlet />
            </React.Suspense>
          </div>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <ScrollRestoration />
    </div>
  );
}

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { Palette, Search } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/AuthContext";

import { visibleNavItems } from "./navigation";

export function useCommandPaletteShortcut(setOpen: React.Dispatch<React.SetStateAction<boolean>>) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);
}

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const items = visibleNavItems(user?.permissions ?? []);
  const go = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-overlay bg-neutral-900/30" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[14vh] z-modal w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border bg-white shadow-md focus:outline-none"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command label="Command palette" loop>
            <div className="flex items-center gap-2 border-b px-4">
              <Search className="size-4 text-neutral-400" aria-hidden="true" />
              <Command.Input autoFocus placeholder="Go to a page…" className="h-12 w-full bg-transparent text-md outline-none placeholder:text-neutral-400" />
              <kbd className="rounded border bg-neutral-50 px-1.5 py-0.5 font-mono text-2xs text-neutral-500">Esc</kbd>
            </div>
            <Command.List className="max-h-80 overflow-y-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-sm text-neutral-500">No matching pages.</Command.Empty>
              <Command.Group heading="Pages" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-neutral-500">
                {items.map((item) => (
                  <Command.Item
                    key={item.id}
                    value={`${item.label} ${item.summary}`}
                    onSelect={() => go(item.to)}
                    className="flex cursor-default items-center gap-3 rounded-md px-2 py-2 text-sm text-neutral-800 data-[selected=true]:bg-accent-50 data-[selected=true]:text-accent-800"
                  >
                    <item.icon className="size-4 text-neutral-500" aria-hidden="true" />
                    <span className="font-medium">{item.label}</span>
                    <span className="truncate text-xs text-neutral-600">{item.summary}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Developer" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-neutral-500">
                <Command.Item
                  value="UI kit components design system"
                  onSelect={() => go("/dev/ui")}
                  className="flex cursor-default items-center gap-3 rounded-md px-2 py-2 text-sm text-neutral-800 data-[selected=true]:bg-accent-50 data-[selected=true]:text-accent-800"
                >
                  <Palette className="size-4 text-neutral-500" aria-hidden="true" />
                  <span className="font-medium">UI kit</span>
                  <span className="truncate text-xs text-neutral-600">Every design-system component with live examples</span>
                </Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

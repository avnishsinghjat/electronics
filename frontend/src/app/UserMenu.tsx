import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, KeyRound, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/AuthContext";
import { ROLE_LABELS } from "@/features/auth/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

const itemClass =
  "flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-neutral-800 outline-none data-[highlighted]:bg-neutral-100";

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className="flex h-8 items-center gap-2 rounded-md px-1.5 text-sm text-neutral-700 hover:bg-neutral-100 focus-visible:shadow-focus focus-visible:outline-none"
      >
        <span className="sr-only">Account menu: </span>
        <span className="flex size-6 items-center justify-center rounded-full bg-accent-600 text-2xs font-semibold text-white" aria-hidden="true">
          {initials(user.full_name) || "?"}
        </span>
        <span className="max-w-[160px] truncate font-medium max-md:sr-only">{user.full_name}</span>
        <ChevronDown className="size-3.5 text-neutral-500" aria-hidden="true" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="z-dropdown min-w-56 rounded-md border bg-white p-1 shadow-md">
          <div className="px-2 py-2">
            <p className="text-sm font-medium text-neutral-900">{user.full_name}</p>
            <p className="font-mono text-xs text-neutral-500">{user.username}</p>
            <p className="mt-1 text-xs text-neutral-600">{user.roles.map((r) => ROLE_LABELS[r]).join(", ")}</p>
          </div>
          <DropdownMenu.Separator className="my-1 h-px bg-neutral-200" />
          <DropdownMenu.Item className={itemClass} onSelect={() => navigate("/change-password")}>
            <KeyRound className="size-4 text-neutral-500" aria-hidden="true" /> Change password
          </DropdownMenu.Item>
          <DropdownMenu.Item className={itemClass} onSelect={() => void logout()}>
            <LogOut className="size-4 text-neutral-500" aria-hidden="true" /> Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { controlClasses, useFieldControl } from "./field";

export interface ComboboxOption {
  value: string;
  label: string;
  /** Secondary line, e.g. manufacturer for an MPN. */
  description?: string;
}

export interface ComboboxProps {
  id?: string;
  value: ComboboxOption | null;
  onChange: (option: ComboboxOption | null) => void;
  /** Server-side search; called (debounced) with the typed query. */
  loadOptions: (query: string, signal: AbortSignal) => Promise<ComboboxOption[]>;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  disabled?: boolean;
  debounceMs?: number;
  monoLabels?: boolean;
  className?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}

/** Result of the last completed search, keyed by the query it answered. */
type LoadState = { query: string | null; options: ComboboxOption[]; error?: string };

export function Combobox(props: ComboboxProps) {
  return <ComboboxInner {...useFieldControl(props)} />;
}

function ComboboxInner({
  id,
  value,
  onChange,
  loadOptions,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No matches",
  disabled,
  debounceMs = 200,
  monoLabels = false,
  className,
  ...aria
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [result, setResult] = React.useState<LoadState>({ query: null, options: [] });
  const loading = open && result.query !== query;
  const state = {
    status: loading ? "loading" : result.error ? "error" : "idle",
    options: result.options,
    error: result.error,
  } as const;

  React.useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      loadOptions(query, controller.signal)
        .then((options) => setResult({ query, options }))
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          setResult({ query, options: [], error: err instanceof Error ? err.message : "Search failed" });
        });
    }, debounceMs);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [open, query, loadOptions, debounceMs]);

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild disabled={disabled}>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
          className={cn(controlClasses, "flex h-9 items-center justify-between gap-2 text-left", !value && "text-neutral-500", className)}
          {...aria}
        >
          <span className={cn("truncate", monoLabels && value && "font-mono")}>{value ? value.label : placeholder}</span>
          <ChevronsUpDown className="size-4 shrink-0 text-neutral-400" />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align="start"
          sideOffset={4}
          className="z-dropdown w-[max(var(--radix-popover-trigger-width),18rem)] rounded-md border bg-white p-0 shadow-md"
        >
          <Command shouldFilter={false} label="Search options">
            <div className="flex items-center gap-2 border-b px-3">
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder={searchPlaceholder}
                className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-neutral-400"
              />
              {state.status === "loading" && <Loader2 className="size-4 animate-spin text-neutral-400" aria-label="Loading" />}
            </div>
            <Command.List className="max-h-64 overflow-y-auto p-1">
              {state.status === "error" ? (
                <div role="alert" className="px-2 py-3 text-sm text-status-red-fg">{state.error}</div>
              ) : state.status !== "loading" && state.options.length === 0 ? (
                <Command.Empty className="px-2 py-3 text-sm text-neutral-500">{emptyText}</Command.Empty>
              ) : null}
              {state.options.map((opt) => (
                <Command.Item
                  key={opt.value}
                  value={opt.value}
                  onSelect={() => {
                    onChange(opt.value === value?.value ? null : opt);
                    setOpen(false);
                  }}
                  className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-neutral-800 data-[selected=true]:bg-accent-50 data-[selected=true]:text-accent-800"
                >
                  <Check className={cn("size-4 text-accent-600", opt.value === value?.value ? "opacity-100" : "opacity-0")} />
                  <span className="min-w-0">
                    <span className={cn("block truncate", monoLabels && "font-mono")}>{opt.label}</span>
                    {opt.description && <span className="block truncate text-xs text-neutral-600">{opt.description}</span>}
                  </span>
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

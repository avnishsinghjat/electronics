import { Minus, Plus } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { controlClasses, useFieldControl } from "./field";

export interface NumberInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type"> {
  value: number | null;
  onValueChange: (value: number | null) => void;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  /** Number of decimals shown and kept; 0 for whole units (pcs). */
  precision?: number;
}

function clamp(n: number, min?: number, max?: number): number {
  if (min !== undefined && n < min) return min;
  if (max !== undefined && n > max) return max;
  return n;
}

/** Numeric field with a unit suffix and +/- steppers. Quantities render in JetBrains Mono. */
export const NumberInput = React.forwardRef<HTMLInputElement, NumberInputProps>(
  ({ value, onValueChange, unit, min, max, step = 1, precision = 0, className, disabled, ...rest }, ref) => {
    const props = useFieldControl(rest);
    const [draft, setDraft] = React.useState(value === null ? "" : value.toFixed(precision));
    const [shown, setShown] = React.useState(value);
    if (value !== shown) {
      setShown(value);
      setDraft(value === null ? "" : value.toFixed(precision));
    }

    const commit = (raw: string) => {
      const cleaned = raw.replace(/,/g, "").trim();
      if (cleaned === "") {
        onValueChange(null);
        return;
      }
      const parsed = Number(cleaned);
      if (Number.isNaN(parsed)) {
        setDraft(value === null ? "" : value.toFixed(precision));
        return;
      }
      const rounded = Number(clamp(parsed, min, max).toFixed(precision));
      onValueChange(rounded);
      setDraft(rounded.toFixed(precision));
    };

    const bump = (dir: 1 | -1) => {
      const next = Number(clamp((value ?? 0) + dir * step, min, max).toFixed(precision));
      onValueChange(next);
    };

    return (
      <div className={cn("relative flex items-stretch", className)}>
        <button
          type="button"
          tabIndex={-1}
          aria-label="Decrease"
          disabled={disabled || (min !== undefined && (value ?? 0) <= min)}
          onClick={() => bump(-1)}
          className="flex w-8 items-center justify-center rounded-l-md border border-r-0 border-neutral-300 bg-neutral-50 text-neutral-600 hover:bg-neutral-100 disabled:opacity-50"
        >
          <Minus className="size-3.5" />
        </button>
        <input
          ref={ref}
          inputMode="decimal"
          role="spinbutton"
          aria-valuenow={value ?? undefined}
          aria-valuemin={min}
          aria-valuemax={max}
          disabled={disabled}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
            if (e.key === "ArrowUp") {
              e.preventDefault();
              bump(1);
            }
            if (e.key === "ArrowDown") {
              e.preventDefault();
              bump(-1);
            }
          }}
          className={cn(controlClasses, "h-9 rounded-none text-right font-mono tabular-nums", unit && "pr-12")}
          {...props}
        />
        {unit && (
          <span className="pointer-events-none absolute right-9 top-1/2 -translate-y-1/2 text-xs text-neutral-500">
            {unit}
          </span>
        )}
        <button
          type="button"
          tabIndex={-1}
          aria-label="Increase"
          disabled={disabled || (max !== undefined && (value ?? 0) >= max)}
          onClick={() => bump(1)}
          className="flex w-8 items-center justify-center rounded-r-md border border-l-0 border-neutral-300 bg-neutral-50 text-neutral-600 hover:bg-neutral-100 disabled:opacity-50"
        >
          <Plus className="size-3.5" />
        </button>
      </div>
    );
  },
);
NumberInput.displayName = "NumberInput";

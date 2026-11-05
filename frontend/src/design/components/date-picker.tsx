import * as PopoverPrimitive from "@radix-ui/react-popover";
import { format, isValid, parse } from "date-fns";
import { CalendarDays } from "lucide-react";
import * as React from "react";
import { DayPicker } from "react-day-picker";
import "react-day-picker/style.css";

import { cn } from "@/lib/utils";

import { controlClasses } from "./field";

export const DATE_FORMAT = "dd MMM yyyy";

export interface DatePickerProps {
  id?: string;
  value: Date | null;
  onChange: (date: Date | null) => void;
  placeholder?: string;
  disabled?: boolean;
  minDate?: Date;
  maxDate?: Date;
  className?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}

/** Date field: type "dd MMM yyyy" (or ISO yyyy-mm-dd) or pick from the calendar. */
export function DatePicker({ id, value, onChange, placeholder = "dd MMM yyyy", disabled, minDate, maxDate, className, ...aria }: DatePickerProps) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState(value ? format(value, DATE_FORMAT) : "");
  const [shown, setShown] = React.useState(value);
  if (value !== shown) {
    // Re-sync the text when the value changes from outside (calendar pick, form reset).
    setShown(value);
    setText(value ? format(value, DATE_FORMAT) : "");
  }

  const commit = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) return onChange(null);
    const parsed = [DATE_FORMAT, "yyyy-MM-dd", "dd/MM/yyyy"]
      .map((f) => parse(trimmed, f, new Date()))
      .find((d) => isValid(d));
    if (parsed) onChange(parsed);
    else setText(value ? format(value, DATE_FORMAT) : "");
  };

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <div className={cn("relative", className)}>
        <input
          id={id}
          value={text}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && commit((e.target as HTMLInputElement).value)}
          className={cn(controlClasses, "h-9 pr-9 tabular-nums")}
          {...aria}
        />
        <PopoverPrimitive.Trigger asChild disabled={disabled}>
          <button
            type="button"
            aria-label="Open calendar"
            className="absolute right-1 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100 disabled:opacity-50"
          >
            <CalendarDays className="size-4" />
          </button>
        </PopoverPrimitive.Trigger>
      </div>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content align="start" sideOffset={4} className="z-dropdown rounded-lg border bg-white p-3 shadow-md">
          <DayPicker
            mode="single"
            selected={value ?? undefined}
            defaultMonth={value ?? undefined}
            onSelect={(d) => {
              onChange(d ?? null);
              setOpen(false);
            }}
            disabled={[...(minDate ? [{ before: minDate }] : []), ...(maxDate ? [{ after: maxDate }] : [])]}
            weekStartsOn={1}
            style={{ "--rdp-accent-color": "#1F4FD8", "--rdp-accent-background-color": "#EEF3FE", fontSize: "13px" } as React.CSSProperties}
          />
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

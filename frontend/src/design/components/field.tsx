import * as LabelPrimitive from "@radix-ui/react-label";
import * as React from "react";

import { cn } from "@/lib/utils";

export const controlClasses =
  "w-full rounded-md border border-neutral-300 bg-white px-3 text-sm text-neutral-900 shadow-xs transition-[border-color,box-shadow] placeholder:text-neutral-500 hover:border-neutral-400 focus-visible:border-accent-600 focus-visible:shadow-focus focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-neutral-50 disabled:text-neutral-500 aria-[invalid=true]:border-status-red-dot aria-[invalid=true]:focus-visible:shadow-[0_0_0_3px_rgba(240,68,56,.18)]";

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn("text-sm font-medium text-neutral-700 peer-disabled:opacity-60", className)}
    {...props}
  />
));
Label.displayName = "Label";

interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}

/** Label + control + hint/error, wired with aria-describedby. */
export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  const describedBy = error ? `${htmlFor}-error` : hint ? `${htmlFor}-hint` : undefined;
  const control = React.isValidElement<Record<string, unknown>>(children)
    ? React.cloneElement(children, {
        id: htmlFor,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
        "aria-required": required || undefined,
      })
    : children;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={htmlFor}>
        {label}
        {required && (
          <span className="ml-0.5 text-status-red-fg" aria-hidden="true">
            *
          </span>
        )}
      </Label>
      {control}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-xs text-status-red-fg" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${htmlFor}-hint`} className="text-xs text-neutral-500">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

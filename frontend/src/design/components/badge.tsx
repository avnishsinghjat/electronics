import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import type { StatusTone } from "@/design/tokens";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-px text-xs font-medium",
  {
    variants: {
      tone: {
        neutral: "border-neutral-200 bg-neutral-50 text-neutral-700",
        accent: "border-accent-200 bg-accent-50 text-accent-700",
        teal: "border-teal-200 bg-teal-50 text-teal-800",
        outline: "border-neutral-300 bg-white text-neutral-700",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

const PILL: Record<StatusTone, string> = {
  grey: "border-status-grey-border bg-status-grey-bg text-status-grey-fg",
  blue: "border-status-blue-border bg-status-blue-bg text-status-blue-fg",
  amber: "border-status-amber-border bg-status-amber-bg text-status-amber-fg",
  green: "border-status-green-border bg-status-green-bg text-status-green-fg",
  red: "border-status-red-border bg-status-red-bg text-status-red-fg",
};
const DOT: Record<StatusTone, string> = {
  grey: "bg-status-grey-dot",
  blue: "bg-status-blue-dot",
  amber: "bg-status-amber-dot",
  green: "bg-status-green-dot",
  red: "bg-status-red-dot",
};

/** Semantic meaning of each tone, used app-wide (CLAUDE.md "UI direction"). */
export const TONE_MEANING: Record<StatusTone, string> = {
  grey: "Not started",
  blue: "In progress",
  amber: "Pending / at risk",
  green: "Done / pass",
  red: "Fail / blocked",
};

export interface StatusPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone: StatusTone;
  children: React.ReactNode;
}

export function StatusPill({ tone, children, className, ...props }: StatusPillProps) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-px text-xs font-medium",
        PILL[tone],
        className,
      )}
      {...props}
    >
      <span className={cn("size-1.5 rounded-full", DOT[tone])} aria-hidden="true" />
      {children}
    </span>
  );
}

/** Part numbers, serials, MPNs and quantities always render in JetBrains Mono. */
export function MonoText({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("font-mono text-[0.92em] tabular-nums tracking-tight", className)} {...props} />;
}

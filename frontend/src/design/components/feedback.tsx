import * as ProgressPrimitive from "@radix-ui/react-progress";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import type { StatusTone } from "@/design/tokens";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn("skeleton-shimmer rounded-md", className)} {...props} />;
}

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: React.ReactNode;
  /** The clear next action (usually one primary Button). */
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {Icon && (
        <div className="mb-4 flex size-11 items-center justify-center rounded-lg border bg-white shadow-xs">
          <Icon className="size-5 text-neutral-500" aria-hidden="true" />
        </div>
      )}
      <h3 className="text-md font-semibold text-neutral-900">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-neutral-500">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

const BAR: Record<StatusTone, string> = {
  grey: "bg-status-grey-dot",
  blue: "bg-accent-600",
  amber: "bg-status-amber-dot",
  green: "bg-status-green-dot",
  red: "bg-status-red-dot",
};

export interface ProgressBarProps {
  value: number;
  max?: number;
  tone?: StatusTone;
  label: string;
  showValue?: boolean;
  className?: string;
}

export function ProgressBar({ value, max = 100, tone = "blue", label, showValue = true, className }: ProgressBarProps) {
  const pct = max <= 0 ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <ProgressPrimitive.Root
        value={value}
        max={max}
        aria-label={label}
        className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-100"
      >
        <ProgressPrimitive.Indicator
          className={cn("h-full rounded-full transition-[width] duration-300", BAR[tone])}
          style={{ width: `${pct}%` }}
        />
      </ProgressPrimitive.Root>
      {showValue && <span className="w-10 text-right font-mono text-xs tabular-nums text-neutral-600">{Math.round(pct)}%</span>}
    </div>
  );
}

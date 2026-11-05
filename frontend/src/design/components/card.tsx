import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { Skeleton } from "./feedback";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} data-card="" className={cn("rounded-lg border bg-white shadow-sm", className)} {...props} />
  ),
);
Card.displayName = "Card";

export function CardHeader({ className, title, description, actions }: {
  className?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-4 border-b px-5 py-3.5", className)}>
      <div className="min-w-0">
        <h3 className="text-md font-semibold text-neutral-900">{title}</h3>
        {description && <p className="mt-0.5 text-sm text-neutral-500">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  /** Change versus the comparison period, e.g. +4.2 (percent) or -3 (count). */
  delta?: number;
  deltaLabel?: string;
  /** Whether an increase is good (green) or bad (red), e.g. "overdue lines" rising is bad. */
  positiveIsGood?: boolean;
  hint?: string;
  loading?: boolean;
  icon?: React.ReactNode;
}

export function StatCard({ label, value, delta, deltaLabel, positiveIsGood = true, hint, loading, icon }: StatCardProps) {
  const direction = delta === undefined || delta === 0 ? 0 : delta > 0 ? 1 : -1;
  const good = direction === 0 ? null : (direction > 0) === positiveIsGood;
  const DeltaIcon = direction > 0 ? ArrowUpRight : direction < 0 ? ArrowDownRight : Minus;
  return (
    <Card className="p-4" aria-busy={loading || undefined}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-neutral-600">{label}</p>
        {icon && <span className="text-neutral-400 [&_svg]:size-4">{icon}</span>}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <p className="mt-1.5 font-mono text-2xl font-semibold tabular-nums tracking-tight text-neutral-900">{value}</p>
      )}
      {(delta !== undefined || hint) && !loading && (
        <div className="mt-1.5 flex items-center gap-1.5 text-xs">
          {delta !== undefined && (
            <span
              data-testid="stat-delta"
              className={cn(
                "inline-flex items-center gap-0.5 font-medium tabular-nums",
                good === null ? "text-neutral-500" : good ? "text-status-green-fg" : "text-status-red-fg",
              )}
            >
              <DeltaIcon className="size-3.5" aria-hidden="true" />
              {delta > 0 ? "+" : ""}
              {delta}
              {deltaLabel ?? ""}
            </span>
          )}
          {hint && <span className="text-neutral-500">{hint}</span>}
        </div>
      )}
    </Card>
  );
}

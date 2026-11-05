import { Check, ChevronRight } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import type { StatusTone } from "@/design/tokens";
import { cn } from "@/lib/utils";

/* ---------------------------------------------------------------- Breadcrumb */

export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumb({ items, className }: { items: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={className}>
      <ol className="flex flex-wrap items-center gap-1 text-xs text-neutral-500">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${item.label}-${i}`} className="flex items-center gap-1">
              {item.to && !last ? (
                <Link to={item.to} className="rounded hover:text-neutral-900 hover:underline focus-visible:shadow-focus focus-visible:outline-none">
                  {item.label}
                </Link>
              ) : (
                <span aria-current={last ? "page" : undefined} className={cn(last && "font-medium text-neutral-700")}>
                  {item.label}
                </span>
              )}
              {!last && <ChevronRight className="size-3 text-neutral-400" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/* ---------------------------------------------------------------- PageHeader */

export interface PageHeaderProps {
  title: string;
  description?: React.ReactNode;
  breadcrumb?: Crumb[];
  /** The page's one primary action, top right. */
  primaryAction?: React.ReactNode;
  secondaryActions?: React.ReactNode;
  meta?: React.ReactNode;
}

export function PageHeader({ title, description, breadcrumb, primaryAction, secondaryActions, meta }: PageHeaderProps) {
  return (
    <div className="mb-6">
      {breadcrumb && <Breadcrumb items={breadcrumb} className="mb-2" />}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">{title}</h1>
          {description && <p className="mt-1 text-sm text-neutral-500">{description}</p>}
          {meta && <div className="mt-2 flex flex-wrap items-center gap-2">{meta}</div>}
        </div>
        {(primaryAction || secondaryActions) && (
          <div className="flex shrink-0 items-center gap-2" data-print="hide">
            {secondaryActions}
            {primaryAction}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Stepper */

export type StepState = "complete" | "current" | "upcoming" | "blocked";

export interface Step {
  id: string;
  label: string;
  state: StepState;
  detail?: string;
}

const STEP_CIRCLE: Record<StepState, string> = {
  complete: "border-status-green-dot bg-status-green-dot text-white",
  current: "border-accent-600 bg-white text-accent-700 ring-4 ring-accent-50",
  upcoming: "border-neutral-300 bg-white text-neutral-500",
  blocked: "border-status-red-dot bg-status-red-bg text-status-red-fg",
};

/** Production stages: horizontal stepper that scrolls on narrow screens. */
export function Stepper({ steps, className }: { steps: Step[]; className?: string }) {
  return (
    <ol className={cn("flex items-start overflow-x-auto pb-1", className)} aria-label="Stages">
      {steps.map((step, i) => (
        <li key={step.id} className="flex min-w-[96px] flex-1 flex-col items-center text-center" aria-current={step.state === "current" ? "step" : undefined}>
          <div className="flex w-full items-center">
            <div className={cn("h-px flex-1", i === 0 ? "bg-transparent" : steps[i - 1]?.state === "complete" ? "bg-status-green-dot" : "bg-neutral-200")} />
            <span
              className={cn("flex size-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold tabular-nums", STEP_CIRCLE[step.state])}
              data-state={step.state}
            >
              {step.state === "complete" ? <Check className="size-3.5" strokeWidth={3} aria-hidden="true" /> : i + 1}
            </span>
            <div className={cn("h-px flex-1", i === steps.length - 1 ? "bg-transparent" : step.state === "complete" ? "bg-status-green-dot" : "bg-neutral-200")} />
          </div>
          <span className={cn("mt-2 px-1 text-xs font-medium", step.state === "upcoming" ? "text-neutral-500" : "text-neutral-800")}>
            {step.label}
            <span className="sr-only"> ({step.state})</span>
          </span>
          {step.detail && <span className="px-1 text-2xs text-neutral-500">{step.detail}</span>}
        </li>
      ))}
    </ol>
  );
}

/* ---------------------------------------------------------------- Timeline */

export interface TimelineEvent {
  id: string;
  title: React.ReactNode;
  timestamp: string;
  actor?: string;
  tone?: StatusTone;
  body?: React.ReactNode;
}

const TIMELINE_DOT: Record<StatusTone, string> = {
  grey: "bg-status-grey-dot",
  blue: "bg-accent-600",
  amber: "bg-status-amber-dot",
  green: "bg-status-green-dot",
  red: "bg-status-red-dot",
};

/** Audit history and key events, newest first. */
export function Timeline({ events, className }: { events: TimelineEvent[]; className?: string }) {
  return (
    <ol className={cn("relative", className)}>
      {events.map((ev, i) => (
        <li key={ev.id} className="relative flex gap-3 pb-5 last:pb-0">
          {i < events.length - 1 && <span className="absolute left-[5px] top-4 h-full w-px bg-neutral-200" aria-hidden="true" />}
          <span className={cn("relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 border-white ring-1 ring-neutral-200", TIMELINE_DOT[ev.tone ?? "grey"])} aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <p className="text-sm font-medium text-neutral-900">{ev.title}</p>
              <time className="text-xs tabular-nums text-neutral-500" dateTime={ev.timestamp}>
                {new Date(ev.timestamp).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
              </time>
            </div>
            {ev.actor && <p className="text-xs text-neutral-500">{ev.actor}</p>}
            {ev.body && <div className="mt-1.5 text-sm text-neutral-700">{ev.body}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

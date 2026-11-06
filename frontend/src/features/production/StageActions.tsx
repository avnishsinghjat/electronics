import { Check, CircleDot, Play, ShieldAlert, X } from "lucide-react";
import * as React from "react";

import { Button, Field, Input, NumberInput, toast } from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { useProductionMutations } from "./api";

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong");

/** Start / pass / fail controls for one unit at one stage. `large` is the shop-floor size. */
export function UnitStageActions({ stageId, unitId, serial, action, requiresQc, large = false, onDone }: {
  stageId: string;
  unitId: string;
  serial: string;
  action: "start" | "finish" | "complete" | null;
  requiresQc: boolean;
  large?: boolean;
  onDone?: () => void;
}) {
  const canProgress = useCan("stage:progress");
  const { progress } = useProductionMutations();
  if (!canProgress) return null;
  const size = large ? "lg" : "sm";
  const run = (a: "start" | "finish" | "complete", passed?: boolean) =>
    progress.mutate(
      { stageId, action: a, serial_unit_id: unitId, passed: passed ?? null },
      {
        onSuccess: (p) => {
          toast.success(
            a === "start" ? `${serial}: ${p.stage_name} started` : p.status === "awaiting_qc" ? `${serial}: waiting for QC` : `${serial}: ${p.stage_name} ${p.qty_failed ? "failed" : "passed"}`,
          );
          onDone?.();
        },
        onError: (e) => toast.error(errMsg(e)),
      },
    );
  const cls = cn(large && "h-16 min-w-40 text-lg [&_svg]:size-6");
  if (action === "start")
    return (
      <Button size={size} className={cls} loading={progress.isPending} onClick={() => run("start")} aria-label={`Start stage for ${serial}`}>
        <Play /> Start
      </Button>
    );
  if (action === "finish" || (action === "complete" && !requiresQc))
    return (
      <span className="flex flex-wrap gap-2">
        <Button size={size} className={cn(cls, "bg-status-green-dot hover:bg-status-green-fg")} loading={progress.isPending} onClick={() => run(action, true)} aria-label={`Pass ${serial}`}>
          <Check /> Pass
        </Button>
        <Button size={size} variant="danger" className={cls} loading={progress.isPending} onClick={() => run(action, false)} aria-label={`Fail ${serial}`}>
          <X /> Fail
        </Button>
      </span>
    );
  if (action === "complete" && requiresQc)
    return (
      <span className={cn("inline-flex items-center gap-2 text-status-amber-fg", large ? "text-lg" : "text-sm")}>
        <ShieldAlert className={large ? "size-6" : "size-4"} aria-hidden="true" /> Waiting for QC inspection
        <Button size={size} variant="secondary" className={cls} loading={progress.isPending} onClick={() => run("complete")}>
          <CircleDot /> Check QC and complete
        </Button>
      </span>
    );
  return null;
}

/** Lot-tracked orders: start a stage for the whole lot, then record passed and failed. */
export function LotStageActions({ stageId, status, unitsIn, requiresQc, stageName }: {
  stageId: string;
  status: string;
  unitsIn: number;
  requiresQc: boolean;
  stageName: string;
}) {
  const canProgress = useCan("stage:progress");
  const { progress } = useProductionMutations();
  const [passed, setPassed] = React.useState<number | null>(unitsIn);
  const [failed, setFailed] = React.useState<number | null>(0);
  const [note, setNote] = React.useState("");
  if (!canProgress) return null;
  const run = (action: "start" | "finish" | "complete") =>
    progress.mutate(
      { stageId, action, qty_passed: action === "start" ? null : passed ?? 0, qty_failed: action === "start" ? null : failed ?? 0, notes: note.trim() || null },
      { onSuccess: () => toast.success(`${stageName}: ${action === "start" ? "started" : action === "finish" ? "waiting for QC" : "completed"}`), onError: (e) => toast.error(errMsg(e)) },
    );
  if (status === "not_started")
    return <Button size="sm" onClick={() => run("start")} loading={progress.isPending}><Play /> Start {stageName}</Button>;
  if (status === "in_progress")
    return (
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Passed" htmlFor={`lp-${stageId}`}><NumberInput className="w-28" value={passed} onValueChange={setPassed} min={0} max={unitsIn} /></Field>
        <Field label="Failed" htmlFor={`lf-${stageId}`}><NumberInput className="w-28" value={failed} onValueChange={setFailed} min={0} max={unitsIn} /></Field>
        <Field label="Note" htmlFor={`ln-${stageId}`}><Input className="w-48" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <Button size="sm" onClick={() => run(requiresQc ? "finish" : "complete")} loading={progress.isPending}>
          {requiresQc ? "Send to QC" : `Complete ${stageName}`}
        </Button>
      </div>
    );
  if (status === "awaiting_qc")
    return (
      <span className="inline-flex items-center gap-2 text-sm text-status-amber-fg">
        <ShieldAlert className="size-4" aria-hidden="true" /> Waiting for QC inspection
        <Button size="sm" variant="secondary" onClick={() => run("complete")} loading={progress.isPending}>Check QC and complete</Button>
      </span>
    );
  return null;
}

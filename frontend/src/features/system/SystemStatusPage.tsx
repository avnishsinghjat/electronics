import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { useHealth, type HealthResponse } from "./api";
import { formatBytes } from "./format";

type Tone = "green" | "amber" | "red" | "grey";

const TONE_CLASSES: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-800 ring-red-200",
  grey: "bg-slate-50 text-slate-700 ring-slate-200",
};

function toneFor(status: string): Tone {
  if (status === "ok") return "green";
  if (status === "degraded") return "amber";
  if (status === "error") return "red";
  return "grey";
}

function Pill({ status, label }: { status: string; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONE_CLASSES[toneFor(status)],
      )}
    >
      {label ?? status.replace("_", " ")}
    </span>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-t py-2.5 first:border-t-0">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-right text-sm">{children}</dd>
    </div>
  );
}

function HealthDetails({ data }: { data: HealthResponse }) {
  return (
    <dl>
      <Row label="Overall">
        <Pill status={data.status} />
      </Row>
      <Row label="Version">
        <span className="font-mono tabular-nums">{data.version}</span>
      </Row>
      <Row label="Database">
        <span className="inline-flex items-center gap-2">
          {data.database.latency_ms !== null && (
            <span className="font-mono tabular-nums text-muted-foreground">
              {data.database.latency_ms.toFixed(1)} ms
            </span>
          )}
          <Pill status={data.database.status} />
        </span>
      </Row>
      <Row label="Free disk in data directory">
        <span className="inline-flex items-center gap-2">
          <span className="font-mono tabular-nums">
            {formatBytes(data.disk.free_bytes)} / {formatBytes(data.disk.total_bytes)}
          </span>
          <Pill status={data.disk.status} />
        </span>
      </Row>
      <Row label="LLM provider">
        <span className="inline-flex items-center gap-2">
          <span className="text-muted-foreground">{data.llm.detail}</span>
          <Pill status={data.llm.status} />
        </span>
      </Row>
      <Row label="Air-gapped mode">
        <Pill status={data.air_gapped ? "ok" : "degraded"} label={data.air_gapped ? "on" : "off"} />
      </Row>
    </dl>
  );
}

export function SystemStatusPage() {
  const health = useHealth();

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12">
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">FabTrack</p>
          <h1 className="text-2xl font-semibold tracking-tight">System status</h1>
        </div>
        <Button
          variant="secondary"
          onClick={() => void health.refetch()}
          disabled={health.isFetching}
          aria-label="Refresh system status"
        >
          <RefreshCw className={cn(health.isFetching && "animate-spin")} />
          Refresh
        </Button>
      </div>

      <section
        aria-labelledby="health-heading"
        className="rounded-xl border bg-card p-5 shadow-[0_1px_2px_rgba(16,24,40,.04),0_4px_12px_rgba(16,24,40,.04)]"
      >
        <h2 id="health-heading" className="sr-only">
          Health
        </h2>
        {health.isPending && (
          <div role="status" aria-label="Loading system status" className="space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-5 animate-pulse rounded bg-muted" />
            ))}
          </div>
        )}
        {health.isError && (
          <div role="alert" className="space-y-1">
            <p className="font-medium text-red-700">Cannot reach the FabTrack API</p>
            <p className="text-sm text-muted-foreground">{health.error.message}</p>
          </div>
        )}
        {health.isSuccess && <HealthDetails data={health.data} />}
      </section>
    </main>
  );
}

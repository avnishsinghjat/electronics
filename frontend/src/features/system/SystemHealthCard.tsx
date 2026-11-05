import { Card, CardContent, CardHeader, Skeleton, StatusPill } from "@/design/components";
import type { StatusTone } from "@/design/tokens";

import type { HealthResponse } from "./api";
import { formatBytes } from "./format";

function tone(status: string): StatusTone {
  if (status === "ok") return "green";
  if (status === "degraded") return "amber";
  if (status === "error") return "red";
  return "grey";
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-t py-2.5 first:border-t-0">
      <dt className="text-sm text-neutral-500">{label}</dt>
      <dd className="text-right text-sm">{children}</dd>
    </div>
  );
}

export function SystemHealthCard({ health }: {
  health: { isPending: boolean; isError: boolean; error: Error | null; data: HealthResponse | undefined };
}) {
  const data = health.data;
  return (
    <Card>
      <CardHeader title="System status" description="Server, database, storage and AI provider" />
      <CardContent>
        {health.isPending && (
          <div role="status" aria-label="Loading system status" className="space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-5" />
            ))}
          </div>
        )}
        {health.isError && (
          <div role="alert" className="space-y-1">
            <p className="font-medium text-status-red-fg">Cannot reach the FabTrack API</p>
            <p className="text-sm text-neutral-500">{health.error?.message}</p>
          </div>
        )}
        {data && (
          <dl aria-label="Health">
            <Row label="Overall">
              <StatusPill tone={tone(data.status)}>{data.status}</StatusPill>
            </Row>
            <Row label="Version">
              <span className="font-mono tabular-nums">{data.version}</span>
            </Row>
            <Row label="Database">
              <span className="inline-flex items-center gap-2">
                {data.database.latency_ms !== null && (
                  <span className="font-mono tabular-nums text-neutral-500">{data.database.latency_ms.toFixed(1)} ms</span>
                )}
                <StatusPill tone={tone(data.database.status)}>{data.database.status}</StatusPill>
              </span>
            </Row>
            <Row label="Free disk in data directory">
              <span className="inline-flex items-center gap-2">
                <span className="font-mono tabular-nums">
                  {formatBytes(data.disk.free_bytes)} / {formatBytes(data.disk.total_bytes)}
                </span>
                <StatusPill tone={tone(data.disk.status)}>{data.disk.status}</StatusPill>
              </span>
            </Row>
            <Row label="LLM provider">
              <span className="inline-flex items-center gap-2">
                <span className="text-neutral-500">{data.llm.detail}</span>
                <StatusPill tone={tone(data.llm.status)}>{data.llm.status.replace("_", " ")}</StatusPill>
              </span>
            </Row>
            <Row label="Air-gapped mode">
              <StatusPill tone={data.air_gapped ? "green" : "amber"}>{data.air_gapped ? "on" : "off"}</StatusPill>
            </Row>
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

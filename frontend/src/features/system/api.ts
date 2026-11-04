import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";

export type ComponentStatus = "ok" | "degraded" | "error";

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  air_gapped: boolean;
  database: { status: ComponentStatus; latency_ms: number | null; detail: string | null };
  disk: {
    status: ComponentStatus;
    path: string;
    free_bytes: number | null;
    total_bytes: number | null;
    detail: string | null;
  };
  llm: {
    status: "not_configured" | "ok" | "degraded" | "error" | "disabled";
    provider: string | null;
    detail: string;
  };
}

export const healthQueryKey = ["system", "health"] as const;

export function useHealth() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => apiGet<HealthResponse>("/health", signal),
    refetchInterval: 30_000,
  });
}

import { Sparkles } from "lucide-react";

import { Tooltip } from "@/design/components";
import { useHealth, type HealthResponse } from "@/features/system/api";
import { cn } from "@/lib/utils";

type Indicator = { tone: "green" | "blue" | "grey"; label: string; detail: string };

/** green = local model ready, blue = online provider in use, grey = off / not configured. */
export function llmIndicator(health: HealthResponse | undefined): Indicator {
  if (!health) return { tone: "grey", label: "AI off", detail: "Server status unknown" };
  const { llm } = health;
  if (llm.status === "ok" && llm.provider === "openrouter") return { tone: "blue", label: "AI online", detail: llm.detail };
  if (llm.status === "ok") return { tone: "green", label: "AI local", detail: llm.detail };
  return { tone: "grey", label: "AI off", detail: llm.detail };
}

const DOT = { green: "bg-status-green-dot", blue: "bg-accent-600", grey: "bg-neutral-400" };

export function LlmStatus() {
  const { data } = useHealth();
  const ind = llmIndicator(data);
  return (
    <Tooltip content={ind.detail} side="bottom">
      <span
        tabIndex={0}
        data-testid="llm-status"
        data-tone={ind.tone}
        className="inline-flex h-8 items-center gap-1.5 rounded-md border bg-white px-2.5 text-xs font-medium text-neutral-700 shadow-xs focus-visible:shadow-focus focus-visible:outline-none"
      >
        <Sparkles className="size-3.5 text-neutral-500" aria-hidden="true" />
        <span className={cn("size-1.5 rounded-full", DOT[ind.tone])} aria-hidden="true" />
        {ind.label}
      </span>
    </Tooltip>
  );
}

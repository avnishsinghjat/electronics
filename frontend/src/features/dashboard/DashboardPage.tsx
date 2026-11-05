import { LayoutDashboard, RefreshCw } from "lucide-react";

import { Button, Card, EmptyState, PageHeader } from "@/design/components";
import { SystemHealthCard } from "@/features/system/SystemHealthCard";
import { useHealth } from "@/features/system/api";

export default function DashboardPage() {
  const health = useHealth();
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home" }]}
        title="Dashboard"
        description="System status now; production, procurement and QC KPIs as their modules go live."
        primaryAction={
          <Button variant="secondary" onClick={() => void health.refetch()} loading={health.isFetching} aria-label="Refresh system status">
            {!health.isFetching && <RefreshCw />}
            Refresh
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <SystemHealthCard health={health} />
        <Card>
          <EmptyState
            icon={LayoutDashboard}
            title="KPIs appear here in Phase 13"
            description="Lines to order, awaiting delivery, overdue PO lines, WIP lots, first-pass yield and open NCRs are computed by the same services as each module, once those modules exist."
          />
        </Card>
      </div>
    </>
  );
}

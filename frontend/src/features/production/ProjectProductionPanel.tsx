import { Factory, Plus } from "lucide-react";
import * as React from "react";

import { Button, Card, DataTable, EmptyState } from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import type { ProjectTree } from "@/features/projects/api";

import { woColumns } from "./ProductionPage";
import { WoDrawer } from "./WoDrawer";
import { useWorkOrders } from "./api";

/** The project's work orders, on the project page. */
export function ProjectProductionPanel({ tree }: { tree: ProjectTree }) {
  const orders = useWorkOrders({ project_id: tree.project.id });
  const canManage = useCan("wo:manage");
  const [creating, setCreating] = React.useState(false);
  const hasBoards = tree.modules.some((m) => m.assemblies.length > 0);
  return (
    <div className="space-y-4">
      {canManage && hasBoards && (
        <div className="flex justify-end">
          <Button onClick={() => setCreating(true)}><Plus /> New work order</Button>
        </div>
      )}
      {orders.data && orders.data.length === 0 ? (
        <Card>
          <EmptyState
            icon={Factory}
            title="No work orders for this project"
            description={hasBoards ? "Create one per PCB assembly lot. It can be released once the module is clear to build." : "Add a module and a PCB assembly first (Overview tab)."}
          />
        </Card>
      ) : (
        <DataTable id="project-work-orders" data={orders.data ?? []} columns={woColumns} getRowId={(w) => w.id} loading={orders.isPending} exportFileName={`${tree.project.code}-work-orders`} />
      )}
      <WoDrawer open={creating} onClose={() => setCreating(false)} project={{ value: tree.project.id, label: tree.project.code, description: tree.project.name }} />
    </div>
  );
}

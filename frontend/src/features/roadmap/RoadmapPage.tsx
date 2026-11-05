import { Construction } from "lucide-react";
import { Link } from "react-router-dom";

import { NAV_ITEMS } from "@/app/navigation";
import { Button, Card, EmptyState, PageHeader } from "@/design/components";

/** Shown for a section whose module is not built yet. States which phase delivers it. */
export default function RoadmapPage({ sectionId }: { sectionId: string }) {
  const item = NAV_ITEMS.find((n) => n.id === sectionId);
  if (!item) throw new Error(`Unknown section ${sectionId}`);
  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Home", to: "/" }, { label: item.label }]}
        title={item.label}
        description={item.summary}
        primaryAction={
          <Button asChild variant="secondary">
            <Link to="/">Back to dashboard</Link>
          </Button>
        }
      />
      <Card>
        <EmptyState
          icon={Construction}
          title={`${item.label} is delivered in Phase ${item.phase}`}
          description={`${item.summary} This section opens once its Phase ${item.phase} gate passes; nothing here is a mock-up.`}
        />
      </Card>
    </>
  );
}

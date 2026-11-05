import { AlertTriangle, Compass } from "lucide-react";
import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

import { Button, Card, EmptyState } from "@/design/components";

export function NotFoundPage() {
  return (
    <Card className="mx-auto mt-12 max-w-xl">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description="The address does not match any FabTrack page. It may have moved, or the link is mistyped."
        action={
          <Button asChild>
            <Link to="/">Go to dashboard</Link>
          </Button>
        }
      />
    </Card>
  );
}

export function ErrorPage({ inShell = false }: { inShell?: boolean }) {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Unknown error";
  return (
    <div className={inShell ? "flex justify-center pt-12" : "app-canvas flex min-h-screen items-center justify-center p-6"}>
      <Card className="w-full max-w-xl">
        <EmptyState
          icon={AlertTriangle}
          title="Something went wrong on this page"
          description={
            <>
              The rest of FabTrack is unaffected. Reload to try again; if it keeps happening, give this message to your administrator:
              <code className="mt-3 block rounded-md border bg-neutral-50 px-3 py-2 text-left font-mono text-xs text-status-red-fg">{message}</code>
            </>
          }
          action={
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => window.location.reload()}>
                Reload page
              </Button>
              <Button asChild>
                <a href="/">Go to dashboard</a>
              </Button>
            </div>
          }
        />
      </Card>
    </div>
  );
}

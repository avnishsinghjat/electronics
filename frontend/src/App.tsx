import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";

import { SystemStatusPage } from "@/features/system/SystemStatusPage";

/** Application root. The routed app shell replaces this single page in Phase 2. */
export function App({ queryClient }: { queryClient: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen">
        <SystemStatusPage />
      </div>
    </QueryClientProvider>
  );
}

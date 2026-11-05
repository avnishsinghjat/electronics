import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { createRouter } from "@/app/router";
import { Toaster, TooltipProvider } from "@/design/components";

const router = createRouter();

export function App({ queryClient }: { queryClient: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <RouterProvider router={router} />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

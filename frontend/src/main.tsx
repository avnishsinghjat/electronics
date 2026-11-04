import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { createQueryClient } from "@/lib/query";
import "@/styles/index.css";

const container = document.getElementById("root");
if (!container) throw new Error("Root element #root not found");

createRoot(container).render(
  <StrictMode>
    <App queryClient={createQueryClient()} />
  </StrictMode>,
);

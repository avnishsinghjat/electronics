import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { apiGet } from "@/lib/api";

import type { Branding } from "./types";

export function useBranding() {
  return useQuery({ queryKey: ["branding"], queryFn: () => apiGet<Branding>("/settings/branding"), staleTime: 60_000 });
}

/** White card centred on the dot-grid canvas, with the company logo slot above it. */
export function AuthLayout({ title, subtitle, children, wide = false }: {
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const branding = useBranding();
  const company = branding.data?.company_name;
  return (
    <main className="app-canvas flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-6 flex flex-col items-center gap-3 text-center">
        {branding.data?.logo_url ? (
          <img src={branding.data.logo_url} alt={company ? `${company} logo` : "Company logo"} className="max-h-14 max-w-[220px] object-contain" />
        ) : (
          <img src="/favicon.svg" alt="" className="size-11" />
        )}
        <div>
          <p className="text-md font-semibold tracking-tight text-neutral-900">{company ?? "FabTrack"}</p>
          <p className="text-xs text-neutral-500">Manufacturing ERP · runs on your local network</p>
        </div>
      </div>
      <section
        aria-labelledby="auth-title"
        data-card=""
        className={`w-full ${wide ? "max-w-2xl" : "max-w-sm"} rounded-lg border bg-white p-6 shadow-sm`}
      >
        <h1 id="auth-title" className="text-xl font-semibold tracking-tight text-neutral-900">
          {title}
        </h1>
        {subtitle && <p className="mt-1 text-sm text-neutral-500">{subtitle}</p>}
        <div className="mt-5">{children}</div>
      </section>
    </main>
  );
}

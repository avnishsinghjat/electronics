/** Deterministic demo data for the UI kit page (not business data). */

export interface DemoPart {
  id: string;
  mpn: string;
  manufacturer: string;
  description: string;
  category: string;
  qty: number;
  unitPrice: number;
  status: "Not ordered" | "Ordered" | "Partially received" | "Received" | "Issued";
}

const MFRS = ["Murata", "Yageo", "Texas Instruments", "STMicroelectronics", "Vishay", "Würth Elektronik", "onsemi", "KEMET"];
const CATS = ["Passive", "IC", "Connector", "Discrete", "Magnetics"];
const STATUSES: DemoPart["status"][] = ["Not ordered", "Ordered", "Partially received", "Received", "Issued"];
const DESCS = ["Cap MLCC 100nF 50V X7R", "Res 10k 1% 0.1W", "MCU ARM Cortex-M4", "Header 2x5 2.54mm", "N-MOSFET 30V 5A", "Inductor 10uH 4.4A"];

/** Linear congruential generator so the demo is identical on every load (stable snapshots). */
function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

export function demoParts(count: number, seed = 42): DemoPart[] {
  const r = rng(seed);
  return Array.from({ length: count }, (_, i) => {
    const cat = CATS[Math.floor(r() * CATS.length)] ?? "Passive";
    return {
      id: `p${i + 1}`,
      mpn: `${cat.slice(0, 2).toUpperCase()}${String(100000 + Math.floor(r() * 899999))}-${String.fromCharCode(65 + (i % 26))}`,
      manufacturer: MFRS[Math.floor(r() * MFRS.length)] ?? "Murata",
      description: DESCS[Math.floor(r() * DESCS.length)] ?? "Part",
      category: cat,
      qty: Math.floor(r() * 5000),
      unitPrice: Math.round(r() * 80000) / 100,
      status: STATUSES[Math.floor(r() * STATUSES.length)] ?? "Ordered",
    };
  });
}

/** Inline SVG "photos" so the UI kit needs no image files or network. */
export function demoPhotoSrc(label: string, hue: number): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${hue},45%,32%)"/><stop offset="1" stop-color="hsl(${hue + 30},50%,18%)"/></linearGradient></defs><rect width="640" height="480" fill="url(#g)"/><g fill="none" stroke="rgba(255,255,255,.35)" stroke-width="3"><rect x="120" y="90" width="400" height="300" rx="12"/><rect x="250" y="190" width="140" height="100" rx="6"/></g><text x="320" y="440" font-family="Inter,sans-serif" font-size="26" fill="rgba(255,255,255,.85)" text-anchor="middle">${label}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

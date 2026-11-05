/**
 * Feature flags for shell elements whose backing feature arrives in a later phase.
 * A flag is turned on by the phase that delivers the feature; Phase 14 removes them.
 * Hidden means hidden: no placeholder buttons (CLAUDE.md rule 3).
 */
export const FEATURES = {
  /** Phase 3: login, user menu, permissions. Live since the Phase 3 gate. */
  auth: true,
  /** Phase 4: project and division switchers in the top bar. Live since the Phase 4 gate. */
  projectSwitcher: true,
  /** Phase 13: entity search (parts, POs, serials) in the command palette. */
  entitySearch: false,
} as const;

export type FeatureName = keyof typeof FEATURES;

/** Project page tabs whose module is not delivered yet. Hidden until their phase passes;
 *  set localStorage `fabtrack.preview-tabs` to "1" to see their "delivered in Phase N"
 *  placeholders (useful when demoing the roadmap). */
export const PROJECT_TABS: Record<string, { label: string; phase: number; live: boolean }> = {
  boq: { label: "BOQ", phase: 5, live: true },
  procurement: { label: "Procurement", phase: 6, live: false },
  production: { label: "Production", phase: 7, live: false },
  qc: { label: "QC", phase: 8, live: false },
  documents: { label: "Documents", phase: 11, live: false },
};

export function isEnabled(name: FeatureName): boolean {
  return FEATURES[name];
}

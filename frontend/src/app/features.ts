/**
 * Feature flags for shell elements whose backing feature arrives in a later phase.
 * A flag is turned on by the phase that delivers the feature; Phase 14 removes them.
 * Hidden means hidden: no placeholder buttons (CLAUDE.md rule 3).
 */
export const FEATURES = {
  /** Phase 3: login, user menu, permissions. */
  auth: false,
  /** Phase 4: project switcher in the top bar (needs the projects API). */
  projectSwitcher: false,
  /** Phase 13: entity search (parts, POs, serials) in the command palette. */
  entitySearch: false,
} as const;

export type FeatureName = keyof typeof FEATURES;

export function isEnabled(name: FeatureName): boolean {
  return FEATURES[name];
}

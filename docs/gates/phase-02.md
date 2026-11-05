# Gate report: Phase 2 (UI design system and app shell)

- Date: 2026-11-05
- Result: **PASS** (`scripts/ci.sh` exit 0)
- Screenshots: [`docs/gates/phase-02/`](phase-02/) (the visual-test baselines)

## What was built

### Design tokens (`frontend/src/design/tokens.ts`)
Single source for the Tailwind theme (`tailwind.config.ts` imports it):
- **Colours**: cool-grey neutral scale (25–900), accent blue (600 = `#1F4FD8`), teal
  (600 = `#0E9F9A`), and the five semantic status tones (grey / blue / amber / green / red)
  with fg, bg, border and dot shades chosen for WCAG AA text contrast.
- **Radius** 6 / 8 / 12; **shadows** xs, sm (the CLAUDE.md layered card shadow), md, focus;
  **font sizes** 11–30 px with line heights (base UI text 14 px, tables 13 px);
  named layout **spacing** (sidebar 240/64, top bar 56, table row 36); **z-index** scale
  (sticky, sidebar, dropdown, overlay, modal, toast, tooltip).

### Canvas and chrome
- CSS-only dot grid on the app canvas (`radial-gradient`, 16 px pitch, dots at 4 % opacity);
  cards are opaque white with a 1 px `#E6E8EC` border and the layered shadow, so the
  texture disappears under them.
- Sidebar `#F8F9FB` with a 1 px divider; white top bar with a bottom border and a
  blue→teal gradient hairline.
- Print stylesheet (`src/styles/print.css`): A4, hides sidebar/top bar/buttons/toasts,
  repeats table headers per page, avoids row breaks; virtualised tables switch to
  rendering every row on `beforeprint`.

### Components (`frontend/src/design/components`, demoed at `/dev/ui`)
Button (primary, secondary, ghost, danger, loading, sizes, asChild) · Field + Label ·
Input · Textarea · NumberInput (unit suffix, steppers, min/max clamp, precision) · Select
(Radix) · Combobox (async debounced search with abort, loading/empty/error) · DatePicker
(type `dd MMM yyyy` / ISO / `dd/MM/yyyy` or pick) · Checkbox (incl. indeterminate) ·
Switch · Badge · StatusPill (5 semantic tones) · MonoText · Card / CardHeader /
CardContent · StatCard (KPI with good/bad-aware delta, loading) · Tabs · Dialog · Drawer ·
Toast (sonner, bundled) · Tooltip · EmptyState · Skeleton · ProgressBar · Breadcrumb ·
PageHeader (breadcrumb, title, one primary action) · Stepper (complete / current /
upcoming / blocked) · Timeline · FileDropzone (type/size validation, drag-drop, tablet
`capture`) · PhotoGrid with lightbox (keyboard nav, evidence metadata) · DataTable.

**DataTable** (TanStack Table + Virtual): sort (ascending first, `aria-sort`), global and
per-column filters, column visibility, column pinning (sticky), row selection with
select-all, saved views (named, stored per browser, try/catch-guarded), CSV export (RFC
4180, UTF-8 BOM for Excel) and XLSX export (typed number/date cells, sticky header row),
exports contain every filtered row in current order; 36 px rows, sticky header, tabular
numerals; tables above 300 rows are virtualised (10,000-row demo on `/dev/ui`).

### App shell
- Collapsible sidebar (Dashboard, Projects, BOQ, Procurement, Inventory, Production, QC,
  Reports, Documents, Design Lab, Settings), state remembered per browser; icon tooltips
  when collapsed; skip-to-content link.
- Top bar: search box that opens the **Ctrl+K command palette** (cmdk; navigates to any
  section and the UI kit), and the **LLM status indicator** (green local, blue online,
  grey off) driven by `/api/health`.
- Routing (React Router 7): lazy-loaded Dashboard and UI kit routes, a roadmap page for
  each section not yet built that states the delivering phase, a 404 page, and an error
  boundary that renders inside the shell so navigation keeps working.
- Dashboard: live System status card (real API) and an empty state stating that KPIs arrive
  in Phase 13.
- User guide: [`docs/user-guide/getting-around.md`](../user-guide/getting-around.md).

## Required tests

| Requirement | Test | Status |
| --- | --- | --- |
| Each component renders and handles disabled / loading / error states | `frontend/tests/design/controls.test.tsx` (19), `display.test.tsx` (20) | pass |
| DataTable: sort, filter, select, export produce correct output on fixture data | `frontend/tests/design/data-table.test.tsx` (13): sort asc/desc, column + global filter, selection callback, hide + pin, CSV byte-exact (BOM, quoting, order), XLSX unzipped and cells checked, saved views, loading/error/empty, 10,000-row virtualisation with full export, print renders all rows | pass |
| axe-core on `/dev/ui` has zero serious violations | `frontend/e2e/a11y.spec.ts` (`/dev/ui`, `/`, `/projects`, 404, open dialog, open command palette; WCAG 2.1 A/AA tags) | pass, 0 serious/critical |
| Playwright visual snapshots of `/dev/ui` and the shell at 1366×768 and 1920×1080 | `frontend/e2e/visual.spec.ts` (dashboard, collapsed sidebar, full `/dev/ui` at both sizes; tolerance 50 px) | pass |

Also: shell tests (`frontend/tests/app.test.tsx`, 8: navigation, Ctrl+K, collapse,
404, error boundary in shell, LLM indicator mapping), offline e2e extended to every shell
route including lazy chunks, print-media e2e.

## Defects found during the gate and fixed

| Defect | Root cause | Fix | Regression test |
| --- | --- | --- | --- |
| Collapsed sidebar links unstyled, arcs drawn beside icons | Radix `Slot` (tooltip trigger) concatenated NavLink's *function* `className` into the class attribute | `SidebarLink` computes active state with `useMatch` and passes a string | `app.test.tsx` "collapses the sidebar…" asserts real classes |
| Visual baseline kept the broken render after the fix | `--update-snapshots` only rewrites failing snapshots and the tolerance (0.2 % of pixels) was too loose to fail | Tolerance tightened to 50 px; baselines regenerated from scratch | visual suite now fails on that size of change |
| axe: 4.47:1 contrast on selected palette rows; combobox placeholder contrast | `neutral-500` text on `accent-50` background; `neutral-400` placeholder | `neutral-600` on highlighted rows, `neutral-500` placeholders | `a11y.spec.ts` |
| axe: label-content-name-mismatch on the top-bar search | `aria-label` differed from visible text | Visible text is the name; `aria-keyshortcuts="Control+K"` | `a11y.spec.ts` |
| Table printed only the visible window; tests saw no rows in jsdom | Virtualiser renders only rows in the viewport | Virtualise only above 300 rows; render all rows while printing | `data-table.test.tsx` printing test |
| Number columns sorted descending first | TanStack `sortDescFirst` defaults to true for numbers | `sortDescFirst: false` | sort test |

## CI summary (`scripts/ci.sh`)

```
==> Offline guard            ok
==> Lint        ruff: All checks passed! · 68 files already formatted · eslint: 0 problems
==> Typecheck   mypy (strict): Success: no issues found in 67 source files · tsc: ok
==> Backend tests      126 passed
==> Frontend unit tests  Test Files 5 passed (5) · Tests 65 passed (65)
==> End-to-end tests   15 passed
CI passed in 58s
```

| Suite | Tests | Coverage |
| --- | --- | --- |
| Backend (pytest) | 126 | 96 % (unchanged) |
| Frontend unit (Vitest + RTL) | 65 | 81.9 % lines, 79.4 % statements, 80.0 % branches; design components 94.3 % lines, DataTable 92.4 % lines |
| End-to-end (Playwright) | 15 | offline 3, axe 5, visual 6, print 1 |
| **Total** | **206** | |

Uncovered frontend code is the `/dev/ui` page and fixtures (exercised by the e2e visual and
axe suites), `main.tsx`, and saved-view storage error branches (private-mode fallbacks).

## Known limits

- **Project switcher and user menu are not shown yet.** They need the projects API
  (Phase 4) and authentication (Phase 3). They are behind flags in
  `src/app/features.ts` rather than shown as non-working controls (rule 3).
- The command palette searches pages only; entity search (MPN, PO, serial, NCR) is
  Phase 13.
- Visual baselines are Linux/Chromium renders; regenerate them
  (`npx playwright test e2e/visual.spec.ts --update-snapshots`) if the CI image changes.
- `/dev/ui` is reachable by any user until Phase 3 adds roles; it shows only demo data.
- The main JS chunk is ~220 kB gzip (design system + Radix + TanStack); feature pages are
  split per route.

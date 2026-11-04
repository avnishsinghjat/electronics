# PROJECT: FabTrack (working name), Offline Electronics Manufacturing ERP with Local LLM

## Mission
Build a production-grade, fully offline web application for a PCB assembly and
electronics module manufacturing unit. It runs on a factory LAN server with no
internet. It tracks every project from BOQ to client handover: what is required,
what is ordered, what is received, what is pending, what is built, what passed QC,
with photo evidence, and produces client-ready QC reports in one click. A local LLM
(LM Studio) drafts documents, writes QC report narratives and assists with KiCad
design evaluation. OpenRouter is an optional online provider. Custom models are
configurable.

## Non-negotiable rules
1. OFFLINE FIRST. No CDN, no Google Fonts, no external scripts, no telemetry.
   All fonts, icons and JS libraries are bundled. The app must fully work with
   the network cable unplugged, except OpenRouter calls.
2. AIR-GAP MODE. An admin setting "Air-gapped mode" disables every outbound
   network call at the gateway level (OpenRouter hidden and blocked). Default ON.
3. NOTHING IS FAKE. No mocked endpoints in production code, no TODO stubs, no
   placeholder buttons. If a feature is in the UI it works end to end.
4. TEST GATES. Each phase ends with unit, API and UI tests that pass. Do not
   start the next phase until `make test` is green and the gate report
   `docs/gates/phase-NN.md` is written (what was built, test counts, coverage,
   known limits).
5. DATA INTEGRITY. Every quantity change is a ledger entry, never an overwrite.
   Every create/update/delete on business records writes an audit log row with
   user, timestamp, before and after JSON.
6. LLM OUTPUT IS A DRAFT. Every LLM-generated document is saved as a draft,
   shown with its source data, and needs a human to approve before it is final.
   The LLM never invents numbers: all quantities, serials, results and dates
   come from the database and are injected as structured context.
7. SMALL, TESTED INCREMENTS. Work module by module. Each module has its own
   router, service, repository, schemas and tests. No cross-module DB access
   except through the other module's service layer.

## Tech stack (do not change without writing an ADR in docs/adr/)
- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic
- Database: PostgreSQL 16 (production), SQLite allowed only in unit tests
- Background jobs: a simple DB-backed job table plus an asyncio worker
  (no Redis dependency); jobs for CSV import, PDF build, LLM calls, KiCad runs
- Files: local disk under DATA_DIR, content-addressed by SHA-256, with a
  files table holding metadata. Thumbnails via Pillow.
- Documents: WeasyPrint (PDF from HTML/Jinja2), python-docx (DOCX), openpyxl (XLSX)
- LLM: OpenAI-compatible HTTP client (httpx) for LM Studio and OpenRouter
- KiCad: kicad-cli (KiCad 8 or 9) and ngspice called as subprocesses in a
  sandboxed working dir with timeouts
- Frontend: React 18, TypeScript (strict), Vite, Tailwind CSS, shadcn/ui
  (Radix primitives), TanStack Query, TanStack Table, React Hook Form + Zod,
  Recharts, lucide-react icons. Inter and JetBrains Mono fonts bundled locally.
- Tests: pytest + pytest-asyncio + httpx AsyncClient, factory_boy, Vitest +
  React Testing Library, Playwright for end-to-end, MSW only in frontend unit tests
- Lint and types: ruff, mypy (strict on services), eslint, tsc --noEmit
- Deployment: Docker Compose (api, worker, web/nginx, postgres), plus a
  bare-metal install script for Ubuntu 22.04/24.04 and Windows notes

## Repository layout
/backend/app/core        config, db, security, audit, files, jobs, errors
/backend/app/modules/<m> router.py, service.py, repo.py, models.py, schemas.py
/backend/tests/<m>       unit and API tests per module
/frontend/src/design     tokens, theme, base components
/frontend/src/features/<m> pages, components, hooks, api client per module
/frontend/tests          unit tests; /e2e Playwright specs
/docs                    adr/, gates/, api/, user-guide/
/deploy                  docker-compose.yml, nginx.conf, install scripts, backup
/samples                 sample BOQ CSVs, sample KiCad project, sample photos

## Domain model (the backbone; refine in Phase 1, do not drop concepts)
Division -> Project -> Module (a deliverable unit) -> PCB Assembly (a board
revision used in the module) -> Build Lot -> Serialised Unit.
BOQ belongs to a Project (and optionally a Module) and has versioned revisions.
BOQ Line -> Part (master part list: MPN, manufacturer, description, package,
category, unit, preferred vendors).
Procurement: Vendor -> Purchase Order -> PO Line (linked to BOQ lines) ->
Goods Receipt (GRN) -> Inventory Ledger.
Production: Work Order -> Stages (kitting, SMT, reflow, AOI, THT, wave/hand
solder, cleaning, conformal coat, programming, functional test, final assy,
packing). Configurable per assembly.
QC: QC Template -> Checklist Items (visual, measurement, functional, document)
-> QC Inspection (per lot or per serial, per stage) -> Results + Photo Evidence
-> NCR (non-conformance) -> Disposition (rework, use-as-is, scrap, return).
Reports: QC Report (draft -> reviewed -> approved -> issued), Document Drafts,
Design Evaluations.

## Status logic for each BOQ line (single source of truth)
required_qty = qty_per_unit x build_qty x (1 + attrition%)
ordered_qty  = sum of open + closed PO lines linked to it
received_qty = sum of accepted GRN qty
issued_qty   = sum of kitting issues to work orders
shortfall    = max(required_qty - ordered_qty, 0)        -> "To order"
pending_rcpt = max(ordered_qty - received_qty, 0)        -> "Awaiting delivery"
Status: Not ordered | Partially ordered | Ordered | Partially received |
Received | Issued. Computed in one service function with unit tests
covering every branch, never duplicated in the frontend.

## Roles
Admin, Project Manager, Purchase, Stores, Production, QC Inspector, QC Lead
(approves reports), Engineer (design/KiCad), Viewer (client-safe read only).
Permissions are checked in the service layer, not only in the UI.

## UI direction (applies to every screen)
- White canvas, never flat: page background #FFFFFF with a very subtle
  cool-grey dot grid or 1px line texture at 3 to 4 percent opacity; content sits
  on white cards with a 1px #E6E8EC border and a soft layered shadow
  (0 1px 2px rgba(16,24,40,.04), 0 4px 12px rgba(16,24,40,.04)).
- Left sidebar in off-white (#F8F9FB) with a 1px divider; top bar white with a
  thin bottom border and a faint gradient hairline accent.
- One primary accent: deep engineering blue (#1F4FD8 range) with a teal
  secondary (#0E9F9A range) for success-adjacent highlights. Status colours are
  semantic and consistent app-wide: grey (not started), blue (in progress),
  amber (pending/at risk), green (done/pass), red (fail/blocked).
- Typography: Inter for UI, JetBrains Mono for part numbers, serials, MPNs
  and quantities. Tabular numerals in all tables.
- Dense but calm data tables (36px rows), sticky headers, column filters,
  saved views, CSV/XLSX export on every table.
- Every page: breadcrumb, page title, one primary action top right, empty
  states with a clear next action, skeleton loaders, toast confirmations.
- Keyboard friendly; WCAG AA contrast; works at 1366x768 and up; tablet
  layout for the QC photo capture screen.

## Definition of done for any feature
Code + migrations + API docs (OpenAPI) + UI + unit tests + API tests + at least
one UI test + seed data so it is visible on a fresh install + user-guide page.

## Working notes (kept current by each phase)
- Phase status lives in `docs/gates/phase-NN.md`. Read the latest gate report
  before starting a new phase.
- Local dev: `make dev` (needs PostgreSQL 16 on localhost:5432, see
  `backend/.env.example`). Full gate: `scripts/ci.sh`.
- Backend venv: `backend/.venv` (Python 3.12). Frontend: `frontend/node_modules`.

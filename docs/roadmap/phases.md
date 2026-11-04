# FabTrack build roadmap: phase prompts

These are the phase prompts the project owner supplied with `CLAUDE.md`. Build them in
order. A phase starts only after the previous gate report (`docs/gates/phase-NN.md`)
is written and `make test` / `scripts/ci.sh` is green.

## Phases 0 to 4: foundation

### Phase 0: scaffold, tooling and test harness (DONE, see docs/gates/phase-00.md)

```text
PHASE 0: Create the repository scaffold exactly as in "Repository layout".

Build:
1. backend/: FastAPI app factory, settings via pydantic-settings (.env), async
   SQLAlchemy engine, health endpoint GET /api/health returning version, db
   status, disk free in DATA_DIR, llm provider status (stub returns
   "not configured" until Phase 9, clearly labelled).
2. Structured JSON logging with request id middleware; global error handler
   returning {error: {code, message, details}} for every failure.
3. frontend/: Vite + React + TS strict + Tailwind + shadcn/ui initialised.
   Fonts (Inter, JetBrains Mono) copied into /public/fonts and loaded via
   @font-face. Zero network requests at runtime (verify in a Playwright test
   that blocks all non-localhost requests and asserts none were attempted).
4. docker-compose.yml with api, worker, web (nginx serving the built SPA and
   proxying /api), postgres with a named volume. Health checks on all four.
5. Makefile targets: dev, test, test-backend, test-frontend, e2e, lint,
   typecheck, migrate, seed, build, package.
6. pytest config with a Postgres test database created per session and
   transactions rolled back per test. Vitest and Playwright configs.
7. scripts/ci.sh that runs lint, typecheck, all tests and fails on any error.

Tests required:
- test_health returns 200 and correct shape
- test_error_handler returns standard error JSON for 404, 422, 500
- Frontend smoke test renders the app root
- Playwright: app loads with network blocked except localhost

Gate: run scripts/ci.sh, paste the summary into docs/gates/phase-00.md.
```

### Phase 1: database schema and data layer

```text
PHASE 1: Implement the full domain model from CLAUDE.md as SQLAlchemy models
and Alembic migrations. Build the shared core, not the business screens.

Build:
1. Base model mixin: id (UUID v7), created_at, updated_at, created_by,
   updated_by, is_deleted (soft delete), row_version (optimistic locking).
2. Tables for every entity in the domain model, with FKs, unique constraints
   (e.g. part MPN + manufacturer, PO number, serial number per assembly),
   check constraints (qty >= 0) and indexes on every FK and status column.
3. Inventory ledger table: part_id, location_id, qty_delta, reason
   (GRN, ISSUE, RETURN, ADJUST, SCRAP), ref_type, ref_id, user, timestamp.
   Stock on hand is ALWAYS computed from the ledger (with a materialised
   balance table refreshed in the same transaction, verified by a test).
4. Audit log table and a SQLAlchemy event hook that writes before/after JSON
   for every insert, update, soft delete on business tables.
5. Files table: sha256, original_name, mime, size, path, uploaded_by,
   linked entity (polymorphic ref_type/ref_id), exif_json, captured_at.
6. Document numbering service: configurable prefixes and yearly sequences
   (e.g. PRJ-2026-0001, PO-2026-0001, GRN-, WO-, QC-, NCR-, RPT-), gap-free,
   concurrency-safe using a sequence table with SELECT ... FOR UPDATE.
7. Generic repository base with pagination, sorting, filtering by whitelisted
   fields, and soft-delete awareness.
8. Seed script: 2 divisions, 3 projects, 4 modules, 5 PCB assemblies, 60 parts,
   5 vendors, realistic Indian vendor names marked as sample data.

Tests required:
- Migrations upgrade and downgrade cleanly on an empty database
- Every constraint rejects bad data (one test per constraint group)
- Audit hook writes correct before/after on update and soft delete
- Ledger: 50 random deltas, balance table equals SUM(ledger) every time
- Numbering: 200 concurrent requests produce 200 unique, gap-free numbers
- Optimistic lock raises a 409 conflict on stale row_version

Gate: docs/gates/phase-01.md with an ER diagram (Mermaid) of all tables.
```

### Phase 2: UI design system and app shell

```text
PHASE 2: Build the design system and app shell before any feature screen.
Follow "UI direction" in CLAUDE.md exactly. The look: white, calm,
engineering-grade, premium. Not plain: texture, depth and hierarchy come from
the subtle grid background, hairline borders, layered soft shadows and precise
typography, not from colour floods.

Build in frontend/src/design:
1. tokens.ts + Tailwind theme: colours (neutral scale, accent blue, teal,
   semantic status), radius (6/8/12), spacing, shadows (xs, sm, md), font
   sizes with line heights, z-index scale.
2. Background: CSS-only dot grid (radial-gradient) at 3 to 4 percent opacity on
   the app canvas, fading out under cards. No images.
3. Components (each with a Storybook-style demo page at /dev/ui and a
   Vitest test): Button (primary, secondary, ghost, danger, loading),
   Input, Select, Combobox (async search), DatePicker, NumberInput with units,
   Textarea, Checkbox, Switch, Badge, StatusPill (the 5 semantic states),
   Card, StatCard (KPI with delta), Tabs, Dialog, Drawer, Toast, Tooltip,
   EmptyState, Skeleton, Breadcrumb, PageHeader, DataTable (TanStack: sort,
   filter, column visibility, pinning, row selection, saved views, export
   CSV/XLSX, virtualised for 10,000 rows), FileDropzone, PhotoGrid with
   lightbox, ProgressBar, Stepper (for production stages), Timeline (for
   audit history), MonoText (MPNs, serials).
4. App shell: collapsible left sidebar (Dashboard, Projects, BOQ, Procurement,
   Inventory, Production, QC, Reports, Documents, Design Lab, Settings),
   top bar with global search (Ctrl+K command palette), project switcher,
   LLM status indicator (green local, blue online, grey off), user menu.
5. Routing with lazy-loaded feature routes, 404 page, error boundary page.
6. Print stylesheet for reports and tables.

Tests required:
- Each component renders, handles disabled/loading/error states
- DataTable: sort, filter, select, export produce correct output on fixture data
- Accessibility: axe-core check on /dev/ui has zero serious violations
- Playwright visual snapshot of /dev/ui and the shell at 1366x768 and 1920x1080

Gate: screenshots of the shell and /dev/ui saved to docs/gates/phase-02/.
```

### Phase 3: authentication, roles and audit

```text
PHASE 3: Local authentication and role-based access. No external identity
provider (offline).

Build:
1. Users table, Argon2id password hashing, login with username/password,
   JWT access token (15 min) + refresh token in httpOnly cookie, logout,
   forced password change on first login, lockout after 5 failed attempts.
2. Roles from CLAUDE.md with a permission matrix defined in one Python module
   (permission strings like "boq:import", "qc:approve_report"). Decorator /
   dependency `require(perm)` used by every router. A user can have multiple
   roles and be scoped to specific divisions or projects.
3. Admin screens: users list, create/edit user, assign roles and scopes,
   reset password, deactivate.
4. Audit log viewer: filter by user, entity, date; diff view of before/after.
5. Frontend: login page (white, centred card on the grid background, company
   logo slot), auth context, route guards, hide actions the user cannot do.
6. First-run setup wizard: create admin, company name, logo upload, document
   number prefixes, data directory check.

Tests required:
- Permission matrix test: every endpoint declares a permission (fail the test
  if any router endpoint lacks `require`)
- Each role can and cannot do the expected actions (table-driven test)
- Project scoping: a user scoped to Project A gets 404 on Project B records
- Lockout, refresh, logout, password change flows
- Playwright: login, wrong password, forced change, logout

Gate: docs/gates/phase-03.md with the permission matrix as a table.
```

### Phase 4: divisions, projects, modules and assemblies

```text
PHASE 4: Project structure. This is the spine every later module hangs on.

Build:
1. CRUD for Divisions, Projects (client, PO ref from client, start date,
   due date, status, project manager, notes), Modules (name, code, qty to
   deliver), PCB Assemblies (board name, revision, layer count, size, finish,
   KiCad project file link, assembly drawing upload, stage template).
2. Project page with tabs: Overview, BOQ, Procurement, Production, QC,
   Documents, Files, History. Tabs not yet built show a proper empty state
   saying which phase delivers them, and are hidden behind a feature flag
   until that phase passes.
3. Projects list grouped by Division with filters (status, PM, client, due
   window) and a division switcher in the top bar.
4. File attachments on any entity using the core files service (drag and
   drop, preview for images and PDF, download, delete with audit).
5. Clone a project (structure only, optional BOQ copy) for repeat orders.

Tests required:
- Service tests for CRUD, validation, clone (deep copy correctness)
- API tests for scoping and permissions
- Playwright: create division -> project -> module -> assembly, attach a file,
  see it in History

Gate: docs/gates/phase-04.md.
```

## Phases 5 to 8: the manufacturing ERP core

### Phase 5: BOQ / BOM with CSV upload and revisions

```text
PHASE 5: BOQ management per project and per module.

Build:
1. BOQ entity with revisions (A, B, C...). Only one revision is "Released";
   older ones are read-only. Every line keeps a stable line_key so changes can
   be diffed across revisions.
2. Manual BOQ editor: spreadsheet-like grid (inline edit, paste from Excel,
   add/remove rows, keyboard navigation), autocomplete against the Part master,
   create a new Part inline if MPN not found.
3. CSV/XLSX import wizard (background job):
   a. Upload file (CSV, XLSX, KiCad BOM CSV export).
   b. Auto-detect delimiter, encoding (UTF-8, UTF-8-BOM, Windows-1252),
      header row.
   c. Column mapping screen with auto-suggested mapping (Ref Des, Qty, MPN,
      Manufacturer, Description, Value, Footprint/Package, DNP, Category,
      Unit, Unit price, Preferred vendor, Notes). Save mapping as a template
      per client.
   d. Validation preview: per row errors (missing MPN, non-numeric qty,
      duplicate ref des, qty does not match ref des count) and warnings
      (unknown part, possible duplicate MPN with different casing/spacing).
   e. Merge rule: lines with same MPN merged, ref des concatenated.
   f. Commit creates a new BOQ revision. Nothing is written before commit.
   g. Downloadable error report CSV.
4. Revision compare: added, removed, qty changed, part substituted, shown as
   a colour-coded diff table; export to XLSX.
5. Build quantity and attrition % per line category (e.g. passives 2 percent,
   ICs 0 percent), editable, feeding required_qty from CLAUDE.md.
6. Line status column using the single status service from CLAUDE.md (will
   show "Not ordered" until Phase 6, that is correct behaviour).
7. Sample files in /samples: clean BOQ, messy BOQ with every error type,
   KiCad BOM export, 2,000-line BOQ for performance.

Tests required:
- Parser tests for every sample, every encoding, every error type
- Mapping template save/apply
- Merge and ref-des count validation
- Revision diff correctness on hand-built fixtures
- required_qty calculation incl. attrition and rounding up to whole units
- Performance: 2,000-line import validated and committed in under 10 s
- Playwright: upload messy CSV, fix mapping, see errors, upload clean CSV,
  commit, compare Rev A vs Rev B

Gate: docs/gates/phase-05.md.
```

### Phase 6: procurement, receiving, inventory and pending tracking

```text
PHASE 6: Complete tracking of what is ordered and what is pending, per
project, per module, per BOQ line.

Build:
1. Vendors: details, GSTIN field, contacts, payment terms, lead time,
   rating, documents.
2. Purchase Requisition: generated from BOQ shortfall (select lines, or
   "all shortfall for this project"), editable, approved by PM.
3. Purchase Orders: from requisitions or manual. PO lines link to one or
   more BOQ lines (one PO line can serve several projects; quantity
   allocation per project is stored explicitly). Expected delivery date per
   line. Statuses: Draft, Issued, Partially received, Received, Closed,
   Cancelled. PO PDF from a Jinja2 template with company letterhead.
4. Goods Receipt Note: receive against PO lines, partial receipts, batch/lot,
   date code, MSL level, CoC upload, photo of packaging/labels, incoming
   inspection result (accept, reject, hold). Only accepted qty posts to the
   inventory ledger. Rejected qty creates a vendor return record.
5. Inventory: locations (stores, bins, MSL dry cabinet, WIP, quarantine),
   stock on hand from ledger, transfers, adjustments with reason (needs
   approval), reservations per project, low-stock alerts.
6. THE TRACKER VIEW (most important screen): per project, a table of every
   BOQ line with required, ordered, received, issued, shortfall,
   awaiting delivery, expected date, vendor, PO numbers (clickable), status
   pill, days overdue. Filters: status, vendor, overdue only, module.
   Group by vendor or category. Header KPIs: % lines fully received,
   lines to order, lines awaiting delivery, overdue lines, value pending.
   Export XLSX. A "Clear to build" indicator per module: green only when
   every line is received in full.
7. Cross-project pending view: all open PO lines across all projects,
   sorted by expected date, for the purchase team's daily follow-up.

Tests required:
- Status service: every transition from CLAUDE.md, including over-receipt,
  cancellation, PO line serving two projects, rejection at GRN
- Ledger consistency after a full PR -> PO -> GRN -> issue cycle
- Clear-to-build logic on edge cases (DNP lines excluded, zero-qty lines)
- Concurrency: two users receiving the same PO line cannot over-receive
- Playwright: shortfall -> PR -> PO -> partial GRN -> tracker shows
  "Partially received" with correct numbers -> final GRN -> "Received"

Gate: docs/gates/phase-06.md with a screenshot of the tracker view.
```

### Phase 7: production work orders and assembly stages

```text
PHASE 7: Shop-floor tracking for PCB assembly and module integration.

Build:
1. Stage templates per PCB Assembly (default list from CLAUDE.md, reorder,
   add custom, mark which stages require a QC inspection before moving on).
2. Work Order: project, module/assembly, build qty, lot number, planned
   dates. Release blocked unless "Clear to build" or a PM override with a
   reason (audited).
3. Kitting: issue parts from inventory to the WO (ledger ISSUE), partial
   kitting allowed, kit shortage list, return unused parts.
4. Serialisation: generate serial numbers by rule (prefix + assembly code +
   year + running number), print labels (PDF with QR codes, generated
   locally), or track by lot only for low-value boards.
5. Stage progress per lot and per serial: start, complete, qty passed,
   qty failed, operator, timestamps, notes. A stage requiring QC cannot be
   completed until its QC inspection passes (enforced in service layer).
6. Shop-floor mode: large-touch tablet layout, scan serial QR with the device
   camera (local JS decoder, no network) to open that unit's current stage.
7. WO board: kanban by stage with counts, and a WO detail with the Stepper
   component and a unit-level genealogy (which part lots went into which
   serial, from kitting records).

Tests required:
- Release blocking and override audit
- Kitting ledger entries and returns
- Serial generation uniqueness and format under concurrency
- Stage gating by QC (cannot bypass via API)
- Genealogy query returns the correct part lots for a serial
- Playwright: release WO -> kit -> progress through 3 stages on tablet viewport

Gate: docs/gates/phase-07.md.
```

### Phase 8: QC with photo evidence

```text
PHASE 8: Quality control with mandatory photo evidence at every QC stage.

Build:
1. QC Templates: per assembly and stage, checklist items with type
   (pass/fail visual, numeric measurement with min/max and unit, text,
   document upload), "photo required" flag and minimum photo count,
   reference image showing what a good result looks like. Versioned.
   Seed templates: incoming inspection, post-reflow visual (IPC-A-610
   Class 2/3 selectable), AOI review, THT solder, conformal coat, programming
   verification, functional test, final inspection, packing.
2. QC Inspection: created automatically when a lot/serial reaches a stage
   that requires QC. Inspector fills each item. Measurements auto-evaluate
   pass/fail against limits. Overall result computed; inspector cannot mark
   pass if any required item fails or a required photo is missing.
3. Photo capture: on tablet use the camera directly (input capture), on
   desktop drag and drop. On upload: SHA-256, EXIF captured_at, server
   timestamp, inspector, linked item; auto thumbnail; optional burn-in
   watermark (project, serial, stage, date/time) on a derived copy while
   the original is kept untouched for evidential integrity. Annotate photos
   (arrow, circle, text) saved as an overlay layer, not destructive.
4. NCR: failed items raise an NCR with defect category (bridging,
   tombstoning, insufficient solder, wrong polarity, missing part, damage,
   etc.), severity, photos, root cause, disposition, rework record, and
   re-inspection link. NCR closure needs QC Lead.
5. Evidence gallery per project: filter by stage, serial, result, defect
   type; every photo shows its full chain (who, when, what item).
6. Evidence integrity check: a job that re-hashes all files and flags any
   mismatch on the dashboard.
7. Storage policy: images resized to max 2560px for the derived copy,
   originals kept, configurable retention.

Tests required:
- Template versioning: old inspections keep their template version
- Pass/fail engine for every item type and limit combination
- Cannot pass with a missing required photo (API level)
- Hash and EXIF extraction on sample JPEG/HEIC/PNG; integrity job detects a
  tampered file
- NCR lifecycle and stage gating with Phase 7
- Playwright tablet viewport: open QC from a serial, take 3 photos (fixture
  images), fail one item, raise NCR, rework, re-inspect, pass

Gate: docs/gates/phase-08.md.
```

## Phases 9 to 12: the LLM layer

### Phase 9: LLM gateway (LM Studio, OpenRouter, custom models)

```text
PHASE 9: A single provider-agnostic LLM gateway in backend/app/core/llm.

Build:
1. Provider abstraction with one interface: list_models(), chat(messages,
   params, stream), chat_json(messages, json_schema), embed(texts),
   health(). All providers speak the OpenAI-compatible API.
2. Providers:
   a. LM Studio (default): base URL http://<host>:1234/v1, no key.
      Uses /v1/models, /v1/chat/completions, /v1/embeddings. Detect
      which models are loaded and show them; clear error if the LM Studio
      server is not running or no model is loaded.
   b. OpenRouter (optional): base URL https://openrouter.ai/api/v1, API key
      stored encrypted at rest (Fernet key from env), sends HTTP-Referer
      and X-Title headers, model list fetched and cached. Blocked entirely
      when Air-gapped mode is ON, enforced in the gateway, not the UI.
   c. Custom: any number of named OpenAI-compatible endpoints (vLLM,
      llama.cpp server, Ollama /v1, an internal GPU server) with base URL,
      optional key, custom headers, timeout, and a manually entered model
      name list for servers that do not expose /models.
3. Model roles: admin assigns a provider + model to each role:
   drafting, qc_report, design_review, vision (photo description, optional),
   embedding, fast (short classifications). Per-role params: temperature,
   max_tokens, context window, JSON mode support flag. Fallback chain per
   role (e.g. LM Studio model A, then custom server B; OpenRouter only if
   air-gap is OFF).
4. Settings UI (Settings > AI Models): provider cards with live status,
   "Test connection", "Send test prompt" with streamed output and tokens/s,
   role assignment table, air-gap toggle with a clear warning.
5. Prompt template library: versioned Jinja2 prompt templates in the DB
   (system + user parts, variables declared with types, linked role),
   editable by Admin with a diff view and a "test with sample data" button.
6. Streaming to the browser via Server-Sent Events, cancellable.
7. Structured output: chat_json uses response_format json_schema where the
   model supports it; otherwise prompt-enforced JSON with a repair-and-
   validate loop (max 2 retries) against a Pydantic model.
8. Context guard: estimate tokens, chunk or summarise inputs that exceed the
   model's window instead of silently truncating.
9. LLM call log: role, provider, model, template version, input hash,
   tokens in/out, latency, status, user. Prompt/response bodies stored only
   if "store LLM transcripts" is enabled.
10. pgvector enabled (use pgvector/pgvector:pg16 image) for later RAG.

Tests required:
- A local fake OpenAI-compatible server (FastAPI in tests/fakes) used by
  tests; never call the real internet in tests
- Provider selection, fallback chain, timeout, retry, cancellation
- Air-gap: with mode ON, any OpenRouter call raises before a socket opens
  (assert with a socket-blocking fixture)
- JSON repair loop with malformed fake responses
- Key encryption round trip; key never returned by any API
- Manual integration test script scripts/llm_smoke.py run against a real
  LM Studio instance, documented in the gate report

Gate: docs/gates/phase-09.md including the smoke test output.
```

### Phase 10: one-click QC report for the client

```text
PHASE 10: Generate a client-ready QC report in one click per project,
module, lot or serial range.

Build:
1. Report data assembler (pure Python, no LLM): pulls project, client,
   assemblies, lots, serials, all inspections with template versions,
   every item result and measurement, NCRs with dispositions, rework
   records, incoming inspection summary, part traceability (lots, date
   codes), photo evidence list with hashes. Output: a typed ReportData object.
2. Statistics (pure Python): first-pass yield per stage, defect Pareto,
   measurement summary (min, max, mean, Cpk where >= 30 samples), open vs
   closed NCRs.
3. LLM narrative (qc_report role) writes ONLY: executive summary,
   observations per stage, NCR summary in plain language, conclusion.
   Input is ReportData as JSON. Output is JSON matching a Pydantic schema.
4. Fact guard: after generation, extract every number, serial, date and
   part number from the narrative and verify each exists in ReportData.
   Any unverified token is highlighted and blocks approval until edited.
5. Report editor: section-by-section view, source data panel beside each
   section, regenerate one section, manual edit, comments.
6. Workflow: Draft -> Reviewed (QC Inspector) -> Approved (QC Lead,
   e-signature = password re-entry + timestamp) -> Issued (locked,
   versioned; changes need a new revision).
7. Output: PDF (WeasyPrint) and DOCX with company letterhead, cover page,
   document control table, contents, summary, results tables, charts
   (rendered server-side to SVG), NCR section, photo evidence appendix
   (thumbnails grid with captions: serial, stage, item, timestamp, hash
   prefix), signature block, and a QR code on each page that encodes the
   report number and SHA-256 of the PDF for verification.
8. Client-safe toggle: hide internal costs, vendor names, internal notes.
9. Verify page: upload a report PDF, the app recomputes the hash and
   confirms it matches an issued report.
10. Works with the LLM disabled: a deterministic template narrative is used
    and labelled "auto-generated summary".

Tests required:
- Assembler and statistics on a seeded project with known answers
- Fact guard catches an injected wrong number and a fake serial
- Workflow permissions and locking after issue
- PDF builds with 500 photos in under 60 s; page count and sections checked
- Hash verification round trip
- Playwright: one click generate -> edit -> review -> approve -> download PDF

Gate: docs/gates/phase-10.md with a sample PDF in docs/gates/phase-10/.
```

### Phase 11: document drafting studio

```text
PHASE 11: LLM-assisted drafting for manufacturing documents.

Build:
1. Document types (each a template with a structured form + prompt +
   output layout): Acceptance Test Procedure, Certificate of Conformance,
   First Article Inspection report, Work Instruction / SOP, Packing List,
   Delivery Note, Test Report, NCR report, Deviation/Concession request,
   DFM feedback to client, technical cover letter, vendor RFQ.
2. Context binding: pick project/module/assembly; the form pre-fills from
   the database (part lists, serials, QC results, dates). LLM fills prose
   only, numbers come from data (reuse the Phase 10 fact guard).
3. Reference library (RAG): upload the company's own standards, past
   reports, client specs (PDF/DOCX). Text extracted locally, chunked,
   embedded with the embedding role, stored in pgvector. Drafts cite the
   chunks they used; citations clickable to the source page.
4. Editor: rich text (TipTap) with section regenerate, tone selector,
   "shorten", "make more formal", track changes vs last version.
5. Approval workflow same as reports; export PDF/DOCX with letterhead.
6. Custom document type builder for Admin: define fields, prompt, layout.

Tests required:
- Each document type renders with seeded data and the LLM fake
- RAG: ingest sample PDF, query returns the right chunk, citation links work
- Fact guard on drafts
- Custom type builder creates a working type end to end

Gate: docs/gates/phase-11.md.
```

### Phase 12: KiCad design evaluation and simulation assistant

```text
PHASE 12: "Design Lab" for the evaluation/design phase using KiCad tools
locally. The LLM explains and prioritises; it never executes free-form
commands.

Build:
1. Upload a KiCad project (zip or folder) to a PCB Assembly revision.
   Detect KiCad version from files; check kicad-cli and ngspice are
   installed and show their versions in Settings.
2. Automated checks via whitelisted kicad-cli subcommands in a sandbox dir
   with timeouts:
   - ERC: kicad-cli sch erc (JSON output)
   - DRC: kicad-cli pcb drc (JSON output, with schematic parity)
   - BOM export, netlist export, position file, Gerbers + drill (zipped)
   - Board renders/3D images where the installed version supports it
3. Parsers turn results into structured findings (severity, rule, location,
   sheet/layer, coordinates). Store per run; compare run N vs run N-1.
4. Fab and assembly capability profiles (editable): min track/space, min
   drill, annular ring, board thickness, min component pitch for the SMT line,
   max board size for the pick-and-place. A DFM/DFA checker parses the
   .kicad_pcb (S-expression parser) and flags violations, plus checks for
   fiducials, test points, polarity marks, courtyard overlaps.
5. BOM cross-check: KiCad BOM vs the project's BOQ revision; mismatches
   listed with one-click "create BOQ revision from KiCad BOM".
6. Simulation: export SPICE netlist (kicad-cli sch export netlist --format
   spice), let the engineer choose analysis (op, tran, ac, dc sweep) and
   probes in a form, run ngspice in batch mode, parse raw output, plot with
   Recharts, and check pass criteria the engineer sets (e.g. rail ripple
   below X mV, rise time below Y us). Simulation runs are saved and
   comparable.
7. LLM design review (design_review role): input is the structured findings,
   DFM results, BOM summary and simulation results as JSON. Output: a
   prioritised review (critical, major, minor), each item linked to the
   underlying finding, with suggested fixes. Also an "Ask about this design"
   chat grounded on the same data. Results exportable as a Design Review
   report (PDF/DOCX) via the Phase 11 engine.
8. Engineer sign-off of a design revision gates release to production
   (Phase 7 WO release checks it).

Tests required:
- Parsers tested on stored kicad-cli JSON outputs (fixtures for KiCad 8 and 9)
- Sandbox: path traversal in uploaded zip is rejected; timeouts enforced;
  only whitelisted commands can run
- DFM checker on a sample board with known violations in /samples
- ngspice run on a sample RC filter circuit; computed cutoff within 2 percent
  of the analytic value
- BOM vs BOQ cross-check
- Integration test (marked, runs when kicad-cli is present) on the sample
  project

Gate: docs/gates/phase-12.md.
```

## Phases 13 to 15: visibility, integration and delivery

### Phase 13: dashboards and project status

```text
PHASE 13: Management visibility. All numbers come from the same service
functions the modules use; no duplicate SQL in dashboard code.

Build:
1. Home dashboard (role-aware): KPI StatCards (active projects, lines to
   order, lines awaiting delivery, overdue PO lines, WIP lots, QC first-pass
   yield this month, open NCRs, reports awaiting approval), "My tasks" list
   (approvals, inspections due, overdue follow-ups).
2. Division view: projects as rows with a progress bar split into
   Procurement %, Production %, QC %, and due-date risk flag.
3. Project overview tab: material readiness donut, stage funnel for all
   lots, QC yield trend, NCR Pareto, timeline of key events, upcoming
   deliveries list.
4. Purchase dashboard: pending by vendor, vendor on-time delivery %, overdue
   ageing buckets (0-7, 8-15, 16-30, 30+ days).
5. QC dashboard: yield by stage and assembly, defect Pareto, inspector
   workload, evidence integrity status.
6. Global search (Ctrl+K): projects, parts by MPN, PO, GRN, serials, NCRs,
   reports, with keyboard navigation.
7. Notifications (in-app, offline): overdue POs, failed QC, report approval
   requests, low stock. Optional SMTP to a LAN mail server if configured.
8. Scheduled XLSX exports (daily project status) written to a shared folder.

Tests required:
- Every KPI tested against a seeded dataset with hand-computed expected values
- Dashboard API under 500 ms with 50 projects, 20,000 BOQ lines, 100,000
  ledger rows (seed a performance dataset)
- Search relevance tests for MPN and serial queries
- Playwright visual snapshots of each dashboard

Gate: docs/gates/phase-13.md.
```

### Phase 14: integration and end-to-end hardening

```text
PHASE 14: Prove the whole system works together. No new features.

Do:
1. Remove all feature flags for completed phases; hidden tabs now live.
2. Golden-path E2E suite (Playwright, against docker compose, real Postgres,
   fake LLM server):
   Admin setup -> create division/project/module/assembly -> import BOQ CSV
   -> compare revision -> PR -> PO -> partial GRN with photos -> tracker
   shows pending -> final GRN -> clear to build -> WO release -> kitting ->
   stages with QC photos -> fail + NCR + rework -> pass -> one-click QC
   report -> approve -> issue -> verify PDF hash -> client Viewer login sees
   only the issued report.
3. Second E2E suite with the real LM Studio (tagged, run manually) using a
   small local model, recording timings.
4. Role matrix E2E: each role logs in and attempts every main action;
   assert allowed/denied.
5. Failure drills: LM Studio down mid-report (graceful error, retry),
   database restart during CSV import (job resumes or fails cleanly),
   disk full on photo upload (clear error, no orphan rows), two users
   editing the same BOQ line (409 with merge prompt).
6. Data consistency checker command: recompute every BOQ status, stock
   balance, and report hash and compare with stored values; must report
   zero discrepancies on the seeded dataset.
7. Security pass: OWASP ASVS L1 checklist, dependency audit (pip-audit,
   npm audit using an offline mirror report), upload validation (magic
   bytes, size limits, zip-bomb guard), rate limits on login, CSP headers.
8. Accessibility and UX pass: axe on every page, keyboard-only walkthrough
   of the golden path, consistent empty states and errors.
9. Fix every defect found; each fix gets a regression test.

Gate: docs/gates/phase-14.md with full test counts, coverage (backend
services >= 85 percent), E2E video of the golden path, list of known issues
(must be empty for severity high).
```

### Phase 15: offline packaging, backup and installer

```text
PHASE 15: Ship it for a factory server with no internet.

Build:
1. Offline bundle: `make package` produces a single folder/tar with all
   Docker images saved (docker save), compose file, .env template, install
   script, and checksums. Install on a clean machine with no internet using
   docker load. Bare-metal alternative: Python wheels and npm build
   vendored, systemd units, nginx config.
2. LM Studio integration guide: install, load a recommended model per role
   (state VRAM/RAM needs), enable the local server on the LAN interface,
   set the URL in Settings. Include a model recommendation table for 8 GB,
   16 GB and 24 GB+ GPUs, and a CPU-only fallback.
3. KiCad + ngspice install guide for the server, and version check page.
4. Backup: nightly pg_dump + DATA_DIR snapshot (rsync with hard links) to a
   configurable path or NAS, 30-day retention, backup status on the
   dashboard. Restore script tested: restore to a fresh machine and run the
   consistency checker.
5. Upgrade path: versioned releases, `upgrade.sh` runs backup first, then
   migrations, then health check, with rollback on failure.
6. HTTPS on LAN: self-signed CA generated at install, instructions to trust
   it on client PCs and tablets (needed for camera access on tablets).
7. Documentation: user guide per role (with screenshots), admin guide,
   troubleshooting (LM Studio not reachable, camera blocked, CSV encoding).

Tests required:
- Fresh VM install from the bundle with networking disabled; golden-path
  E2E passes
- Backup -> wipe -> restore -> consistency checker reports zero issues
- Upgrade from previous tag with seeded data succeeds; rollback drill works

Gate: docs/gates/phase-15.md and a RELEASE_NOTES.md.
```

## Appendix

### Fix prompt (use when a phase gate fails)

```text
The Phase NN gate failed. Do not start new features.
1. Run scripts/ci.sh and list every failing test with its error.
2. For each failure, state the root cause in one line before changing code.
3. Fix the cause, not the test. Only change a test if it asserts the wrong
   behaviour according to CLAUDE.md, and explain why.
4. Add a regression test for every bug that was not already covered.
5. Re-run the full suite (not only the failing tests).
6. Update docs/gates/phase-NN.md with what failed, why, and what changed.
Stop when the suite is green.
```

### Change request prompt (for new features after release)

```text
Read CLAUDE.md and the latest gate reports. New requirement: <describe>.
First write a short design note in docs/adr/ covering affected modules,
schema changes, permissions, UI screens and tests. Wait for my approval.
Then implement with migrations, tests at every layer, and a regression run
of the Phase 14 golden-path E2E. Write docs/gates/cr-<slug>.md.
```

### Release checklist (run on the target server with the network cable unplugged)

- Fresh install from the offline bundle completes without internet
- Browser dev tools show zero requests to any non-LAN host
- Air-gapped mode ON blocks OpenRouter at the gateway
- LM Studio connected, every model role passes "Send test prompt"
- BOQ import of the messy sample shows every expected error
- Tracker view numbers match a hand count on one project
- Tablet camera capture works over HTTPS on the shop floor Wi-Fi
- QC report PDF generated, approved, issued and hash-verified
- Client Viewer role sees only issued, client-safe content
- kicad-cli ERC/DRC and an ngspice run succeed on the sample project
- Nightly backup ran, and a restore drill passed the consistency checker
- All gate reports 00 to 15 present with green test summaries

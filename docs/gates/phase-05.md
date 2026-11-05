# Gate report: Phase 5 (BOQ / BOM with CSV upload and revisions)

- Date: 2026-11-05
- Result: **PASS** (`scripts/ci.sh` exit 0, 178 s)

## What was built

### Backend (`app/modules/boq`, `app/modules/parts`)
- **BOQ and revisions**:
  - a BOQ belongs to a project, and optionally a module and a PCB assembly;
  - the build quantity defaults to the module's quantity to deliver;
  - revisions are lettered A, B, C… (then AA…) and are draft, released or superseded:
    one draft at a time, and releasing supersedes the previous released revision;
  - released and superseded revisions are read-only (409);
  - a new revision copies the current one, keeping its line keys;
  - a draft can be deleted.
- **Line editing**:
  - `PUT /boq-revisions/{id}/lines` replaces the full line set, matched by stable
    `line_key`: existing keys are kept, new rows get new keys, and a duplicated key in the
    payload gets a fresh one;
  - lines link to parts by normalised MPN;
  - attrition comes from the category unless the line overrides it;
  - validation errors are returned per line (`invalid_lines`, with line numbers).
- **Import wizard as background jobs** (`boq.parse`, `boq.validate`):
  - the upload is stored content-addressed;
  - parse detects encoding (UTF-8, UTF-8-BOM, Windows-1252), delimiter (`, ; tab |`),
    XLSX sheet and header row;
  - mapping is suggested from header synonyms, or auto-applied from a saved per-client
    template whose headings match;
  - validate produces every error and warning in the brief plus `qty_from_ref_des`,
    `invalid_price`, `mapping_incomplete`, `no_rows` and `merged` info, merging by
    MPN + manufacturer + DNP;
  - commit is refused while errors exist. It fills an empty draft or creates the next
    revision, reuses line keys from the previous revision (same MPN + manufacturer, else
    same first ref des), creates unknown
    parts in one batch, and can set the build quantity and release.
  - Nothing is written to BOQ lines before commit.
  - The error report CSV is downloadable (BOM-prefixed for Excel).
- **Compare** by line key: added, removed, qty changed, part substituted, edited (with the
  changed fields) and unchanged, plus a summary.
- **Quantities and status**: `app/modules/boq/status.py` is the single implementation of
  `required_qty` (attrition, rounded up to whole units for countable units, to 0.01
  otherwise, 0 for DNP) and the line status. Ordered quantity comes from procurement's
  service (PO-line allocations). Received and issued stay 0 until Phases 6 and 7, so lines
  show "Not ordered", as the brief expects.
- **Parts**:
  - `GET /parts` search ranks exact matches, then prefix, then contains;
  - `POST /parts` (inline create) rejects a duplicate normalised MPN + manufacturer.
- **Seed data**: a new idempotent seeder `seed_sample_boqs` adds **PLC CPU board BOM
  (Sample)** on the sample PLC rack's CPU board. Revision A (released, 11 lines) and
  revision B (draft) differ by one quantity change, one substitution, one removed DNP line
  and one added line, so compare has something to show on a fresh install.
- **Migration 0004**:
  - tables: `boq_imports`, `boq_mapping_templates`;
  - columns: `boq_lines.attrition_override`, `boq_revisions.attrition_by_category`,
    `company_settings.attrition_defaults`.

### Frontend (`src/features/boq`)
- **BOQ tab on the project page**:
  - BOQ picker and revision tabs with status pills;
  - actions: Compare, Import file, New revision, New BOQ (start empty, or create and
    import), Delete draft, Save lines, Release revision.
- **Build quantity and attrition card**, with one rate per category used in the revision.
- **Released revisions**: a read-only DataTable showing Required, To order and the
  server-computed Status, with export.
- **Draft grid** (`BoqGrid`):
  - inline cells and Enter/arrow navigation (Enter on the last row adds a row);
  - Excel TSV paste that grows rows;
  - MPN suggestions from the part master, and "Create part" inline;
  - remove row, and highlighting of server-rejected lines;
  - virtualised above 200 rows.
- **Import wizard** (Upload → Map columns → Check → Commit):
  - detection badges and header-row picker;
  - saved-mapping picker and per-field column selects with sample values;
  - decimal-comma and save-mapping options;
  - stat cards, a blocking banner and an issues table (export, error report CSV);
  - build quantity and release-on-commit.
- **Compare dialog**: From/To selects, colour-coded change pills, a diff table
  ("changes only" by default) with CSV/XLSX export.
- **BOQ page** (`/boq`): every BOQ across visible projects with its current revision, linking
  to the project's BOQ tab.
- User guide: [BOQ](../user-guide/boq.md). Screenshots are in [`phase-05/`](phase-05/).

## Required tests

| Requirement | Test | Status |
| --- | --- | --- |
| Parser tests for every sample, every encoding, every error type | `tests/boq/test_importer.py`: clean CSV, XLSX with title row, messy Windows-1252 (every error and warning code asserted by row), KiCad BOM, semicolon UTF-8-BOM with decimal comma and metres, 2,000-line sample, unreadable files | pass |
| Mapping template save/apply | `test_mapping_template_round_trip_survives_column_reorder` (unit); `test_mapping_templates_save_and_auto_apply` (API: save on validate, auto-applied to a reordered file, apply on demand, delete) | pass |
| Merge and ref-des count validation | `test_split_ref_des`, `test_qty_from_ref_des_when_missing_and_missing_qty_error`, `test_non_countable_units_skip_ref_des_count_check`, `test_mpn_variant_within_file_and_merge_disabled`, `test_dnp_and_fitted_lines_of_same_mpn_do_not_merge` | pass |
| Revision diff correctness on hand-built fixtures | `test_import_clean_then_rev_b_and_compare` (`boq-clean.csv` → `boq-clean-rev-b.csv`: exactly 1 added, 1 removed, 1 qty changed, 1 substituted, 12 unchanged, with line keys carried over); `test_boq_revision_lifecycle_and_lines` (hand-edited revisions); `test_sample_boq_seed_is_visible_and_compares` | pass |
| required_qty incl. attrition and rounding up to whole units | `tests/boq/test_status.py::test_required_qty` (countable vs metres, DNP, zero build), `test_every_status_branch` (all 7 statuses), `test_ordered_quantity_flows_into_status` (PO allocations → Partially ordered / Ordered) | pass |
| Performance: 2,000-line import validated and committed in under 10 s | `test_two_thousand_line_import_under_ten_seconds`: upload, parse, validate and commit of `boq-2000.csv` (2,000 new parts) in **2.5 s** | pass |
| Playwright: upload messy CSV, fix mapping, see errors, upload clean CSV, commit, compare Rev A vs Rev B | `frontend/e2e/boq.spec.ts`. The messy file is detected as Windows-1252 with header row 4. The test unmaps MPN (14 errors), fixes the mapping (5 errors: `invalid_qty`, `missing_mpn`, `duplicate_ref_des`…), downloads the error report, commits `boq-clean.csv` as released Rev A (15 lines, build 50), commits `boq-clean-rev-b.csv` as draft Rev B, and compares: Added 1, Removed 1, Qty changed 1, Part substituted 1 | pass |

Also:
- **e2e**: grid editing and release in `boq.spec.ts`; an axe scan (WCAG 2 A/AA) of the
  mapping and review steps with 0 violations.
- **Frontend unit tests**, `tests/boq.test.tsx` (13), covering:
  - clipboard parsing, row round-trip, DNP and override parsing;
  - the empty state and New BOQ;
  - read-only released revision with server status;
  - grid typing, Enter/arrow navigation, TSV paste and save payload with line keys;
  - MPN suggestions linking a part;
  - server line errors;
  - release; compare (changes only, then all);
  - the full wizard flow (upload → poll → remap → errors block → remap → commit + release);
  - a failed parse; the BOQ list page.

## Defects found during the gate and fixed

| Defect | Root cause | Fix | Regression test |
| --- | --- | --- | --- |
| 2,000-line import took 8.6 s (12.6 s under coverage), too close to the 10 s limit | Each new part was flushed on its own: 2,000 flushes, each running the audit hooks | `parts.create_for_import` takes the whole batch, assigns ids client-side and flushes once | `test_two_thousand_line_import_under_ten_seconds` (now 2.5 s) |
| "Save" for build quantity stayed disabled until the number field lost focus; clicking the disabled button does not blur it, so the change could not be saved by mouse | `NumberInput` only reported its value on blur/Enter | Valid numbers are reported while typing (empty/garbage still settle on commit) | `controls.test.tsx` "reports valid numbers while typing"; `boq.spec.ts` grid test |
| Two "Import file" buttons when a BOQ had no revision | Toolbar and empty state both offered it | Toolbar button only once a revision exists | `boq.spec.ts` (strict locator) |
| Long BOQ names wrapped inside the picker; attrition card listed all 12 categories | Select value not truncated; card showed every category with a stored rate | Select values truncate (design system); the card shows the categories the revision uses | screenshots in `phase-05/` |
| Issues table wider than the wizard dialog (Code column cut off) | Column widths summed past the dialog width | Narrower Field/Problem/Code columns | screenshot `phase-05/import-review.png` |
| Visual snapshots changed with test order | The top bar's division switcher appears once two divisions exist, and other specs create divisions | `stubDivisions` gives visual tests a fixed division list; baselines regenerated (diff: switcher only) | `visual.spec.ts` |
| Phase 4 projects e2e flaky | Toast opened under the pointer (the dialog's bottom-right button); hover kept the stack expanded over the next target | Spec moves the pointer away before the next click | `projects.spec.ts` passed with `--repeat-each=3` |

## CI summary (`scripts/ci.sh`)

```
==> Offline guard            ok
==> Lint        ruff: All checks passed! · 125 files already formatted · eslint: 0 problems
==> Typecheck   mypy (strict): Success: no issues found in 124 source files · tsc: ok
==> Backend tests      250 passed
==> Frontend unit tests  Test Files 9 passed (9) · Tests 110 passed (110)
==> End-to-end tests   31 passed
CI passed in 178s
```

| Suite | Tests | Coverage |
| --- | --- | --- |
| Backend (pytest) | 250 (BOQ 31 new: importer 16, status 3, API 12) | 94 % overall; boq status 100 %, importer 97 %, router 95 %, jobs 94 %, service 86 %; parts service 80 % |
| Frontend unit (Vitest) | 110 (BOQ 13, NumberInput 1 new) | 80 % lines overall; `features/boq` 80.8 % |
| End-to-end (Playwright) | 31 | adds the Phase 5 journey, grid edit and release, and the wizard axe check |
| **Total** | **391** | |

## Known limits

- Company-wide attrition defaults (`company_settings.attrition_defaults`) seed new revisions
  but are not yet editable in Settings. Rates are edited per revision on the BOQ tab. A
  settings screen for them is planned with the Phase 15 admin settings.
- Received and issued quantities are 0 until goods receipts (Phase 6) and kitting
  (Phase 7) exist, so statuses stop at "Ordered". That is the behaviour the brief expects.
- XLSX import reads the first worksheet. To import another sheet, move it first or save it
  as its own file.
- Imported revisions match lines to the previous revision by MPN + manufacturer + DNP, then
  by first ref des. A line whose MPN *and* first ref des both changed shows as removed +
  added rather than substituted.
- Preferred vendor in a file is kept as a line note. Vendor matching arrives with
  procurement in Phase 6.

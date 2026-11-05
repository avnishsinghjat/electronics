# Gate report: Phase 4 (divisions, projects, modules and assemblies)

- Date: 2026-11-05
- Result: **PASS** (`scripts/ci.sh` exit 0, 129 s)

## What was built

### Backend
- **CRUD** for divisions, projects, modules and PCB assemblies (`app/modules/org`):
  - project codes from document numbering (`PRJ-yyyy-nnnn`);
  - optimistic locking: `row_version` in the body for PATCH, a query parameter for DELETE;
  - validation: dates in order, active project manager, unique codes (module per
    project, assembly code + revision per module), layers 1–64, positive sizes, valid
    stage template, assembly file links must be files attached to that assembly;
  - children-first deletion (409 `has_children`);
  - the default stage template is applied to new assemblies.
- **Scoping** on every read and write: out-of-scope records and divisions return 404. Scoped
  users cannot create divisions or move projects out of scope.
- **Project listing** with division/PM names and module counts. Filters: status list,
  division, project manager, client, name/code search, due window (`due_after`,
  `due_before`, `overdue`). Sorting is whitelisted. There is also a `/tree` endpoint
  (project, modules, assemblies) and a `/history` endpoint (audit of the project subtree,
  including files, with human-readable labels).
- **Clone** (`POST /projects/{id}/clone`) copies:
  - modules and live assemblies;
  - drawing and KiCad file links, as new metadata rows over the same content-addressed
    bytes;
  - optionally, each BOQ's current revision (released, else latest) as a new draft
    revision A with stable `line_key`s.

  Procurement, production and QC records are never copied.
- **Attachments** (`app/modules/attachments`):
  - a per-record-type resolver registry (division, project, module, assembly; later
    phases register theirs), with scope checks through the owning record;
  - upload with a size limit (`FABTRACK_MAX_UPLOAD_MB`, default 100) and type sniffed
    from magic bytes, never the browser's claim;
  - list, metadata, download and inline preview for PNG/JPEG/WebP/GIF/PDF only, served
    with `nosniff` and a sandboxing CSP;
  - soft delete (audited), blocked while an assembly links the file.
- **Lookups**: stage templates; a staff directory for pickers. New permissions:
  `directory:read` and `projects:history`, granted to internal roles but not the client
  Viewer.

### Frontend
- **Projects** page:
  - filters for status (open by default), project manager, client and due window;
  - projects grouped by division, one DataTable each (export and saved views included),
    with overdue flags;
  - a new/edit project drawer (React Hook Form + Zod) and a Divisions drawer.
- **Top bar**: a division switcher (remembered per browser; filters lists, and the
  dashboards in Phase 13) and a "Jump to project" switcher. Both were behind flags since
  Phase 2 and are now enabled.
- **Project page**:
  - header with status, overdue and sample-data badges, Clone, Delete and Edit;
  - Overview tab: details plus the modules and assemblies structure, with add, edit and
    delete drawers and confirmations;
  - Files tab: the Attachments component;
  - History tab: a timeline;
  - BOQ, Procurement, Production, QC and Documents tabs are defined in `PROJECT_TABS` and
    hidden until their phase passes. Setting localStorage `fabtrack.preview-tabs = 1` shows
    their "delivered in Phase N" placeholders.
- **Attachments component**:
  - drag-and-drop upload;
  - a list showing size, uploader, time and hash prefix;
  - authenticated preview: image in a dialog, PDF in an iframe from a blob URL (nginx CSP
    gains `frame-src 'self' blob:`);
  - download and delete with confirmation.
- **Assembly drawer**: all board fields plus an assembly-files area, and pickers for the
  drawing and the KiCad project.
- User guide: [projects](../user-guide/projects.md).

## Required tests

| Requirement | Test | Status |
| --- | --- | --- |
| Service tests for CRUD, validation, clone (deep-copy correctness) | `tests/org/test_org_crud.py` (full structure CRUD with audit, validation rules, list filters/grouping fields, lookups), `tests/org/test_clone.py` (structure, file links re-pointed, BOQ from released revision with line keys, original untouched, without-BOQ variant, date validation) | pass |
| API tests for scoping and permissions | `tests/org/test_org_access.py` (scoped PM: 404 on 7 out-of-scope operations, cannot create in or move to other divisions, cannot create divisions; viewer/stores/QC inspector get 403 on all writes; viewer cannot read history), `tests/org/test_attachments.py` (scope and permission for upload, list, download, delete) | pass |
| Playwright: create division → project → module → assembly, attach a file, see it in History | `frontend/e2e/projects.spec.ts` (also links the drawing and checks the project appears under its division) | pass |

Also: `tests/org/test_history.py`; frontend unit tests in `tests/projects.test.tsx`
covering:
- grouping and filters sent to the API;
- create-project validation and payload;
- read-only users seeing no create actions;
- the overdue rule;
- project tabs, structure and history;
- the preview-tabs flag;
- adding a module and an assembly;
- clone, out-of-scope 404, attachments upload and delete, and both switchers.

There is also an axe check on the projects list and project page.

## Defects found during the gate and fixed

| Defect | Root cause | Fix | Regression test |
| --- | --- | --- | --- |
| Dropdowns inside drawers/dialogs opened *behind* them | Popover z-index (30) below modals (50) | Token order: overlay 40 < modal 50 < dropdown 60 < toast 70 < tooltip 80 | `display.test.tsx` "Layering"; `projects.spec.ts` selects a division inside the drawer |
| Labels of Select/DatePicker/NumberInput not associated when wrapped in react-hook-form `Controller` | `Field` cloned its *direct* child only | `Field` provides a context; every control reads it (`useFieldControl`) | `projects.test.tsx` uses `getByLabelText` on Controller-wrapped fields |
| After a failed request the shared test session was unusable / expired test objects | Test override reused one session for all requests | Each request gets its own savepoint session on the test connection, like production; production `get_session` also rolls back explicitly on error | whole backend suite (194) runs on the new harness |
| Closed assembly drawer queried attachments with an invalid id (422 in console) | Query not conditional | `useAttachments(refType, null)` disables the query | console-error check in manual run; drawer tests |

## CI summary (`scripts/ci.sh`)

```
==> Offline guard            ok
==> Lint        ruff: All checks passed! · 111 files already formatted · eslint: 0 problems
==> Typecheck   mypy (strict): Success: no issues found in 110 source files · tsc: ok
==> Backend tests      194 passed
==> Frontend unit tests  Test Files 8 passed (8) · Tests 96 passed (96)
==> End-to-end tests   28 passed
CI passed in 129s
```

| Suite | Tests | Coverage |
| --- | --- | --- |
| Backend (pytest) | 194 (org/attachments 12 new) | 96 % overall; org service 94 %, attachments 95 %, boq copy 84 % |
| Frontend unit (Vitest) | 96 | 79.7 % lines |
| End-to-end (Playwright) | 28 | adds the Phase 4 journey and project-page axe check |
| **Total** | **318** | |

## Known limits

- Deleting is children-first; there is no cascade "delete project with everything".
- File bytes are never removed from the content-addressed store on delete (other records
  may share them); storage retention policy arrives with Phase 8.
- Attachment listing requires `projects:read`; modules from Phase 5 on register their own
  record types and permissions.
- Due-window filters use the browser's date; the server has no time-zone setting yet.

# Gate report: Phase 3 (authentication, roles and audit)

- Date: 2026-11-05
- Result: **PASS** (`scripts/ci.sh` exit 0, 96 s)
- Decisions: [ADR 0003](../adr/0003-authentication.md)

## What was built

### Backend
- **Users, roles, scopes, sessions** (migration `0003`): `users` (case-insensitive unique
  username, Argon2id hash, active flag, forced-change flag, lockout fields), `user_roles`,
  `user_scopes` (division / project), `refresh_tokens` (hashed, rotated, family =
  session), `company_settings` (singleton). Semantic user references across the schema
  (project manager, approvers, inspector, operator, uploader, ledger user, audit actor,
  job creator) are now indexed foreign keys to `users`.
- **Auth API** (`/api/auth`): `login` (15-min JWT + httpOnly SameSite=Strict refresh
  cookie), `refresh` (rotation, reuse ⇒ whole session revoked), `logout`, `me`,
  `change-password` (ends other sessions). Lockout after 5 failures for 15 minutes.
  Forced password change blocks every other endpoint with 403
  `password_change_required`. Each request verifies the session is still live, so logout,
  deactivation and password resets take effect immediately.
- **Permission matrix** in one module (`app/core/permissions.py`, 52 permissions, 9 roles,
  table below); `require(perm)` / `authenticated` / `public` route dependencies; services
  re-check permissions; division/project scoping returns 404 outside scope.
- **User admin API** (`/api/users`): list/search, create (temporary password returned once),
  edit name/email/roles/scopes with optimistic locking, reset password (unlocks, ends
  sessions), deactivate/activate; guards against removing the last admin and
  self-deactivation; role and permission catalogue endpoints.
- **Audit viewer API** (`/api/audit`): filter by user, record type, record id, action and
  date range; paginated; actor names joined. Security events (`login`, `login_failed`,
  `locked`, `logout`) are written explicitly; password hashes are always `[redacted]`.
- **Settings and first-run setup**: `/api/setup/status` (data directory check, default
  prefixes), `/api/setup` (only while no user exists, advisory-locked, signs the admin in),
  company details, logo upload (PNG/JPEG/WebP by magic bytes, ≤ 2 MB, served with sniffed
  type), document-number prefixes, public branding for the login page.
- **Org read API**: `/api/divisions`, `/api/projects`, `/api/projects/{id}`, scope-aware
  (Phase 4 adds the write side).

### Frontend
- API client keeps the access token in memory, renews it once on 401 (single-flight) and
  signs out with a notice if renewal fails.
- Login page (white card on the dot grid, company logo slot), forced/voluntary password
  change page, first-run **setup wizard** (data directory → company and admin → document
  prefixes → logo), route guards, `/forbidden` page, role-aware landing (a client Viewer
  lands on Projects).
- User menu in the top bar (name, roles, change password, sign out); sidebar and command
  palette show only sections the user's permissions allow.
- **Settings**: General (company, logo, numbering), Users (DataTable, create/edit drawer
  with roles and division/project scopes, temporary-password dialog, reset / deactivate /
  activate with confirmation), Audit log (filters, server paging, before/after diff drawer).
  Actions the user may not perform are not rendered.
- User guide: [signing in](../user-guide/signing-in.md),
  [administration](../user-guide/admin-users-and-audit.md).

## Required tests

| Requirement | Test | Status |
| --- | --- | --- |
| Every endpoint declares a permission (fails if any lacks `require`) | `tests/auth/test_permission_matrix.py::test_every_endpoint_declares_a_permission` (+ exactly one rule per route, public list pinned to 8 endpoints, unknown permissions rejected) | pass |
| Each role can and cannot do the expected actions (table-driven) | `tests/auth/test_roles.py::test_role_can_and_cannot[<role>]` × 9 roles × 10 endpoints, plus multi-role union and service-layer enforcement without the router | pass |
| Project scoping: user scoped to Project A gets 404 on Project B | `tests/auth/test_scoping.py` (project scope, division scope, unscoped/admin, filters) | pass |
| Lockout, refresh, logout, password change flows | `tests/auth/test_auth_flows.py` (20: lockout and expiry, refresh rotation and reuse detection, expired refresh, logout revocation, deactivation, tampered/forged/expired JWTs, forced change, password policy, other sessions ended, audit redaction, login events without version bump) | pass |
| Playwright: login, wrong password, forced change, logout | `frontend/e2e/login.spec.ts` (login with `next` redirect, reload keeps session, logout; wrong password ×5 → lockout; new user with temporary password → forced change → start page) | pass |

Also: user admin (7), setup/settings (6), audit API (1) backend tests; frontend unit tests
for sign-in, lockout message, safe redirects, forced change, single-flight token renewal,
session-expiry sign-out, user menu, setup wizard (happy path and bad data dir), role-aware
navigation, users admin, general settings and audit log (`tests/auth.test.tsx`,
`tests/settings.test.tsx`, `tests/app.test.tsx`); e2e for user creation → audit diff and
prefix change (`settings.spec.ts`). Playwright global setup completes the **setup wizard
through the real UI** on a freshly recreated database every run.

## Defects found during the gate and fixed

| Defect | Root cause | Fix | Regression test |
| --- | --- | --- | --- |
| Admin edits of a user who had just signed in failed with 409 | Login bookkeeping went through the ORM and bumped `row_version` | Core `UPDATE`s for login fields + explicit audit events | `test_login_events_are_audited_without_bumping_row_version` |
| Deliberate sign-out landed on `/login?next=…` | The route guard redirected (remembering the page) before the menu's navigation ran | Auth state records a user-initiated sign-out; the guard only remembers the page after expiry | `login.spec.ts` asserts `/login` exactly |
| axe: label-content-name-mismatch on the account menu | `aria-label` differed from the visible name | Visible name is the accessible name, with an `sr-only` "Account menu:" prefix | `a11y.spec.ts` (10 views) |
| Backend coverage under-reported (64 % on auth service) | coverage.py did not follow SQLAlchemy's greenlets | `concurrency = ["greenlet", "thread"]` | numbers below are now accurate |

## CI summary (`scripts/ci.sh`)

```
==> Offline guard            ok
==> Lint        ruff: All checks passed! · 100 files already formatted · eslint: 0 problems
==> Typecheck   mypy (strict): Success: no issues found in 99 source files · tsc: ok
==> Backend tests      182 passed
==> Frontend unit tests  Test Files 7 passed (7) · Tests 83 passed (83)
==> End-to-end tests   26 passed
CI passed in 96s
```

| Suite | Tests | Coverage |
| --- | --- | --- |
| Backend (pytest) | 182 (auth 56) | 96 % overall; services: auth 93 %, users 93 %, settings 90 %, org 85 %, audit 100 %, auth deps 100 % |
| Frontend unit (Vitest) | 83 | 81.3 % lines |
| End-to-end (Playwright) | 26 | a11y 10, visual 8, login 3, offline 3, settings 2 |
| **Total** | **291** | |

## Permission matrix

Generated from `app/core/permissions.py` by `scripts/permission_matrix.py`.

| Permission | Meaning | Admin | PM | Purch | Stores | Prod | QC Insp | QC Lead | Eng | Viewer |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `users:read` | View users | ✓ | ✓ |  |  |  |  |  |  |  |
| `users:manage` | Create, edit, deactivate users; reset passwords; assign roles and scopes | ✓ |  |  |  |  |  |  |  |  |
| `audit:read` | View the audit log | ✓ |  |  |  |  |  |  |  |  |
| `settings:read` | View company settings and document numbering | ✓ | ✓ |  |  |  |  |  |  |  |
| `settings:manage` | Change company settings, logo and document numbering | ✓ |  |  |  |  |  |  |  |  |
| `divisions:read` | View divisions | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `divisions:manage` | Create and edit divisions | ✓ | ✓ |  |  |  |  |  |  |  |
| `projects:read` | View projects, modules and assemblies (within scope) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `projects:manage` | Create, edit, clone projects, modules and assemblies | ✓ | ✓ |  |  |  |  |  |  |  |
| `files:upload` | Attach files to records | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `files:delete` | Delete attached files | ✓ | ✓ |  |  |  |  |  |  |  |
| `boq:read` | View BOQs and revisions | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `boq:edit` | Edit BOQ lines | ✓ | ✓ |  |  |  |  |  | ✓ |  |
| `boq:import` | Import BOQ CSV/XLSX | ✓ | ✓ |  |  |  |  |  | ✓ |  |
| `boq:release` | Release a BOQ revision | ✓ | ✓ |  |  |  |  |  |  |  |
| `parts:read` | View the part master | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `parts:manage` | Create and edit parts | ✓ | ✓ | ✓ |  |  |  |  | ✓ |  |
| `procurement:read` | View vendors, requisitions, POs, GRNs and the tracker | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `vendors:manage` | Create and edit vendors | ✓ |  | ✓ |  |  |  |  |  |  |
| `pr:create` | Raise purchase requisitions | ✓ | ✓ | ✓ |  |  |  |  |  |  |
| `pr:approve` | Approve purchase requisitions | ✓ | ✓ |  |  |  |  |  |  |  |
| `po:manage` | Create, issue, cancel purchase orders | ✓ |  | ✓ |  |  |  |  |  |  |
| `grn:create` | Receive goods (GRN) and record incoming inspection | ✓ |  |  | ✓ |  | ✓ |  |  |  |
| `inventory:read` | View stock and the ledger | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `inventory:transfer` | Transfer stock between locations | ✓ |  |  | ✓ |  |  |  |  |  |
| `inventory:adjust` | Request stock adjustments | ✓ |  |  | ✓ |  |  |  |  |  |
| `inventory:approve_adjustment` | Approve stock adjustments | ✓ |  |  |  |  |  | ✓ |  |  |
| `production:read` | View work orders and stage progress | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `wo:manage` | Create and plan work orders | ✓ | ✓ |  |  | ✓ |  |  |  |  |
| `wo:release` | Release work orders that are clear to build | ✓ | ✓ |  |  | ✓ |  |  |  |  |
| `wo:override_release` | Release a work order that is not clear to build (with reason) | ✓ | ✓ |  |  |  |  |  |  |  |
| `kitting:issue` | Issue and return kit parts | ✓ |  |  | ✓ | ✓ |  |  |  |  |
| `stage:progress` | Record stage progress on the shop floor | ✓ |  |  |  | ✓ |  |  |  |  |
| `qc:read` | View inspections, NCRs and evidence | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `qc:inspect` | Perform QC inspections and upload evidence | ✓ |  |  |  |  | ✓ | ✓ |  |  |
| `qc:manage_templates` | Create and version QC templates | ✓ |  |  |  |  |  | ✓ |  |  |
| `ncr:raise` | Raise NCRs | ✓ |  |  |  |  | ✓ | ✓ |  |  |
| `ncr:close` | Disposition and close NCRs | ✓ |  |  |  |  |  | ✓ |  |  |
| `reports:read` | View QC reports in all states | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `reports:read_issued` | View issued, client-safe QC reports | ✓ |  |  |  |  |  |  |  | ✓ |
| `reports:create` | Generate and edit QC report drafts | ✓ | ✓ |  |  |  | ✓ | ✓ |  |  |
| `reports:review` | Mark QC reports reviewed | ✓ |  |  |  |  | ✓ | ✓ |  |  |
| `reports:approve` | Approve and issue QC reports (e-signature) | ✓ |  |  |  |  |  | ✓ |  |  |
| `documents:read` | View document drafts | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `documents:draft` | Draft documents with the LLM | ✓ | ✓ | ✓ |  |  | ✓ | ✓ | ✓ |  |
| `documents:approve` | Approve documents | ✓ |  |  |  |  |  | ✓ |  |  |
| `design:read` | View design evaluations | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |
| `design:run` | Upload KiCad projects and run checks/simulations | ✓ |  |  |  |  |  |  | ✓ |  |
| `design:signoff` | Sign off a design revision for production | ✓ |  |  |  |  |  |  | ✓ |  |
| `llm:use` | Use AI drafting features | ✓ | ✓ | ✓ |  |  | ✓ | ✓ | ✓ |  |
| `llm:manage` | Configure AI providers, models and prompts | ✓ |  |  |  |  |  |  |  |  |
| `dashboard:read` | View dashboards | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  |

Columns: Admin = Admin, PM = Project Manager, Purch = Purchase, Stores = Stores, Prod = Production, QC Insp = QC Inspector, QC Lead = QC Lead, Eng = Engineer, Viewer = Viewer (client).

## Known limits

- Login rate limiting per IP is a Phase 14 security-pass item; per-account lockout is in
  place now.
- The refresh cookie is not `Secure` until LAN HTTPS is configured (Phase 15:
  `FABTRACK_COOKIE_SECURE=true`).
- Scope restrictions apply to projects and divisions now; each later module applies them
  to its own records (BOQ, POs, work orders, QC) through the org service.
- No self-service password reset (offline server, no mail by default): an administrator
  resets passwords.
- The project switcher (top bar) still waits for Phase 4.

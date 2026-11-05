# ADR 0003: Local authentication, sessions and permissions (Phase 3)

- Status: Accepted
- Date: 2026-11-05

## Decisions

1. **Passwords**: Argon2id (19 MiB memory, 2 iterations, 1 lane — OWASP baseline) via
   argon2-cffi. Hashes are transparently upgraded on login if parameters change. Unknown
   usernames are verified against a dummy hash so timing does not reveal which accounts
   exist. Policy: 10+ characters, not only letters or only digits, must not contain the
   username, must differ from the current one (enforced server-side, mirrored in the UI).
2. **Access token**: JWT HS256, 15 minutes, signed with `FABTRACK_SECRET_KEY` (the API
   refuses to start in production without a random 32+ character key). Kept in browser
   memory only, never in localStorage.
3. **Refresh token**: random 48-byte secret in an `httpOnly`, `SameSite=Strict` cookie
   scoped to `/api/auth`; only its SHA-256 is stored. Rotated on every refresh. A refresh
   token *family* is the session; presenting an already-rotated token revokes the whole
   family (stolen-token detection). `Secure` is enabled with `FABTRACK_COOKIE_SECURE=true`
   once LAN HTTPS exists (Phase 15).
4. **Immediate revocation**: every authenticated request checks that its session family
   still has a live refresh token, so logout, deactivation, password reset and password
   change take effect at once, not after the 15-minute access-token lifetime. One indexed
   query per request is acceptable on a LAN server.
5. **Lockout**: 5 consecutive failures lock the account for 15 minutes (configurable);
   an admin password reset unlocks it. Login bookkeeping (`failed_logins`,
   `locked_until`, `last_login_at`) is written with Core `UPDATE`s so it does **not** bump
   `row_version` (admins editing an active user would otherwise get spurious 409s); each
   outcome is instead an explicit audit event (`login`, `login_failed`, `locked`,
   `logout`). Password hashes are redacted (`__audit_redact__`) in every audit image.
6. **Permissions** live in one module (`app/core/permissions.py`): permission strings,
   role → permission sets, and labels. Routers declare exactly one of
   `Depends(require("perm"))`, `Depends(authenticated)` or `Depends(public)`; a test walks
   every route and fails if one is missing, and pins the list of public endpoints.
   Services re-check (`principal.require(...)`) so the rule holds without the router.
7. **Scoping**: `user_scopes` rows restrict a user to divisions and/or projects; a
   division scope includes all its projects; no rows (or the Admin role) means
   unrestricted. Out-of-scope records return **404**, not 403, so scoped users cannot
   confirm that other projects exist.
8. **First-run setup** is a public endpoint that works only while the `users` table is
   empty, serialised with a PostgreSQL advisory lock so two simultaneous submissions
   cannot both succeed.
9. **Actor foreign keys**: semantic user references (project manager, inspector, approver,
   uploader, ledger user, audit actor, job creator, …) are now FKs to `users` (indexed).
   `created_by` / `updated_by` on every business table stay without FKs: they are always
   stamped from the authenticated principal, users are never hard-deleted (only
   deactivated), and 2 × ~40 extra FK checks and indexes on every write buy nothing extra.
   This refines ADR 0002 item 8.
10. **Logo uploads** accept PNG, JPEG or WebP only (checked by magic bytes, served with the
    sniffed type and `nosniff`), never SVG, because the logo is served from the app origin.

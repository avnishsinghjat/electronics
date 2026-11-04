# ADR 0002: Data layer conventions (Phase 1)

- Status: Accepted
- Date: 2026-11-04

## Decisions

1. **Ids are UUIDv7** generated in Python (`app.core.ids.uuid7`, RFC 9562 layout with a
   monotonic 12-bit counter). Python 3.12 has no `uuid.uuid7`. Time-ordered ids keep
   indexes compact and sort roughly by creation time.
2. **Status and enum columns are `VARCHAR(32)` + a CHECK constraint** generated from a
   Python `StrEnum` (`enum_check`), not PostgreSQL `ENUM` types. Adding a value is a
   one-line migration that replaces a CHECK, instead of `ALTER TYPE` which cannot run in a
   transaction on older servers and cannot remove values.
3. **Uniqueness under soft delete uses partial unique indexes** (`WHERE is_deleted = false`)
   for natural keys a user may re-create after deleting (division/project/vendor codes,
   part MPN + manufacturer, serial per assembly). Document numbers (PO, GRN, WO, QC, NCR,
   RPT) are unique across all rows, deleted or not: a number is never reused.
4. **Part uniqueness ignores case and spaces**: unique index on
   `upper(replace(mpn,' ',''))`, `upper(coalesce(manufacturer,''))`.
5. **Optimistic locking**: `row_version` is SQLAlchemy's `version_id_col`, so a concurrent
   writer gets `StaleDataError` (mapped to HTTP 409). Services also compare the client's
   `row_version` before writing (`Repository.update(..., expected_version=)`) so a stale
   form is rejected even when no concurrent write is in flight.
6. **Audit** is written by a session `after_flush` hook with before-images captured in
   `before_flush` (the mapper bumps `row_version` and `updated_at` without attribute
   history). Audit rows are inserted on the same connection, so they commit or roll back
   with the change.
7. **Inventory ledger is append-only**, enforced by a database trigger
   (`inventory_ledger_immutable`) and a CHECK that ties the sign of `qty_delta` to the
   reason (GRN/RETURN > 0, ISSUE/SCRAP < 0). `stock_balances` is updated in the same
   transaction after a `SELECT ... FOR UPDATE` on the balance row; `verify_balances()`
   recomputes SUM(ledger) for the Phase 14 consistency checker.
8. **Actor columns** (`created_by`, `updated_by`, `project_manager_id`, ...) are plain UUID
   columns until the users table exists; Phase 3 adds the foreign keys.
9. **Document numbering** uses a `(doc_type, year)` counter row locked with
   `SELECT ... FOR UPDATE` inside the caller's transaction: gap-free because a rolled
   back transaction also rolls back its increment.
10. **Jobs** use a `jobs` table claimed with `FOR UPDATE SKIP LOCKED`; a job's own work runs
    in a separate session from its status updates, so a failing job's writes roll back while
    its failure is still recorded.

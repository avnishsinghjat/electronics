# ADR 0005: Production tracking, kitting and serials (Phase 7)

- Status: Accepted
- Date: 2026-11-06

## Decisions

1. **One work order = one assembly = one lot.**
   - A work order snapshots the assembly's stage template into its own stages, so
     template edits never change running orders.
   - Its build lot holds the quantity.
2. **Release gate = the tracker's clear-to-build** for the work order's module (one rule,
   computed by the procurement tracker).
   - An override needs `wo:override_release` (Project Manager, Admin) and a reason.
   - The reason is stored on the work order and written as an explicit
     `release_override` audit event with the readiness at that moment.
3. **Kitting posts through the ledger against BOQ lines** (`issue_to_boq_line` /
   `return_from_boq_line`, built in Phase 6).
   - This is what the status service reads as "issued".
   - `kit_issues` keeps the work order and the part lot of each movement for genealogy.
   - Issues consume the project's reservations oldest first; returns re-reserve.
   - A line cannot be issued beyond the order's own requirement (quantity per unit ×
     build quantity × (1 + attrition), rounded up, from the status service).
4. **Genealogy is per work order.** Parts are kitted to the order, not to each board, so
   every unit of an order shares the order's net lots. Unit-level traceability (which
   reel fed which board) would need feeder scanning at the placement machine, which is
   outside this phase.
5. **Serials**: `{prefix}-{ASSEMBLY CODE}-{year}-{5-digit running number}`.
   - The running number comes from `serial_sequences` (assembly, year), incremented
     under `SELECT … FOR UPDATE`. Concurrent generation is gap-free and unique; the
     concurrency test fails without the lock.
   - The prefix is a company setting.
6. **Stage progress**:
   - Serial tracking: one row per unit per stage. Lot tracking: one row per lot per
     stage, with passed/failed quantities; only passed units flow on.
   - Unique indexes stop duplicate rows.
   - Actions: `start` → in progress; `finish` → awaiting QC (QC stages); `complete` →
     completed.
   - Completing a QC stage requires a **passed** inspection for that stage, of the unit
     or of its whole lot, checked in the service. Stage, work order and lot statuses are
     derived after every change.
7. **Shop floor**:
   - QR codes are decoded in the browser with jsQR, bundled; no network is used.
   - Camera access needs a secure context, so plain-HTTP LAN installs use a handheld
     scanner or typed serials until Phase 15 adds HTTPS.
   - Labels are generated server-side with segno (QR as SVG) and WeasyPrint.
8. **PDF fetcher**: WeasyPrint 70 requires a `URLFetcher` subclass. `app/core/pdf.py`
   allows only bundled template files and data URIs, and fails the render on anything
   else.
9. **DataTable cells are called, not mounted.**
   - TanStack's `flexRender` mounts a cell function as a component. Pages define columns
     inside components, so every re-render remounted every cell, and a click landing
     during a data refresh was lost.
   - Cell renderers are now called as functions, and must not use hooks (render a
     component from the cell when one is needed).

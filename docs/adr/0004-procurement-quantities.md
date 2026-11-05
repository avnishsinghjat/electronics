# ADR 0004: Procurement quantities, receiving rules and the PO PDF (Phase 6)

- Status: Accepted
- Date: 2026-11-05

## Decisions

1. **Allocations follow the line key, not the line row.** A PO line is allocated to BOQ
   lines through `po_line_allocations`, each holding its own project. When the tracker or
   the status column reads a BOQ line, it sums allocations over every line with the same
   stable `line_key` in any revision of that BOQ. Orders placed against revision A
   therefore still count once revision B is released, and nobody has to re-allocate.
2. **What counts as ordered.**
   - Allocations on issued, partially received, received and closed orders count, as
     CLAUDE.md requires.
   - Draft orders do not: they have not been sent. Quantity on drafts and on open
     requisitions is shown separately as "being ordered", and is subtracted when a new
     requisition is raised, so it is never requisitioned twice.
   - For a cancelled PO line, only what was already received counts: cancelling cancels
     the undelivered remainder.
3. **What counts as received.**
   - Only accepted quantity counts, and only accepted quantity posts to the ledger
     (CLAUDE.md rule 5 and the Phase 6 brief).
   - Accepted quantity is spread over the PO line's allocations, oldest first, each up to
     what it still lacks. Each share is stored in `grn_allocations`, posted as its own
     ledger row with the project, and reserved for that project. Anything beyond the
     allocations becomes free stock.
   - The split is written once, at receipt, so later edits to allocations never rewrite
     history.
4. **Rejects and holds.**
   - Rejected quantity creates a vendor return and stays outstanding on the PO line, so
     the vendor owes a replacement.
   - Quantity on hold counts against the PO line, so it cannot be received twice, but not
     as received.
   - Resolving a hold moves quantity to accepted (posted and allocated) or rejected (a
     return), audited on the GRN line.
5. **No over-receipt.**
   - Receiving locks the purchase order row (`SELECT … FOR UPDATE`) for the whole
     transaction, so concurrent receipts of the same order are serialised.
   - Accepted plus on-hold quantity may not exceed what is outstanding.
   - `tests/procurement/test_concurrency.py` races eight receipts on real connections; the
     same test fails when the lock is removed.
   - Extra quantity a vendor ships beyond the order is a commercial decision: issue a PO
     line for it first.
6. **PO PDF is rendered in the request, on a worker thread.**
   - The stack note lists "PDF build" among the background jobs. A purchase order is a
     one- to three-page document that WeasyPrint renders in well under a second.
   - It is rendered with `asyncio.to_thread` so the event loop is not blocked, and
     returned directly.
   - The fetcher refuses every URL that is not a bundled template file or a data URI, so
     the PDF cannot reach the network.
   - QC reports (Phase 10), which embed many photos, will use the job queue as planned.
7. **First-run setup creates reference data.**
   - Stock locations and the default stage template are created by the setup wizard (as
     well as by `make seed`), so a fresh installation can receive goods straight away.
   - Sample data stays opt-in, through the seed command.

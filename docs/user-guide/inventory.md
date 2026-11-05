# Inventory

Stock in FabTrack is never typed in. Every change is a row in the append-only
**ledger**: goods receipts, transfers, approved adjustments and (from Phase 7) issues to
production and returns. Stock on hand is the sum of the ledger.

## Stock

**Inventory → Stock** shows, per part:

- **On hand**: everywhere, including quarantine.
- **Usable**: stores, bins and the MSL cabinet. Quarantine, scrap and WIP stock is not
  usable.
- **Reserved**: set aside for projects.
- **Available**: usable − reserved.
- **Low**: available is below the part's **minimum stock**. Set the minimum with the
  sliders icon (Purchase, Project Managers, Engineers, Admin). **Low stock only** lists
  the alerts.

**Reserve** (bookmark icon) sets free stock aside for a project. Goods received against a
project's PO are reserved for it automatically. Reservations are listed under
**Reservations**, where they can be released.

## By location

Stock per part and location, as the stores team sees it.

- **Move** (arrows icon) transfers a quantity to another location, for example to the MSL
  cabinet for a bake-out, or to quarantine. Project reservations follow the stock.
- **Adjust** (sliders icon) records a counted quantity that differs from the system, with
  the reason.

## Adjustments need approval

An adjustment request changes nothing until someone else approves it: a QC Lead or an
Admin, and never the person who asked. Approval posts the ADJUST entry to the ledger;
rejection leaves stock as it was. Pending requests are under **Adjustments**.

## Ledger

Every movement, newest first: date, movement type, part, location, change (+/−), lot,
project, note and the person who made it. Filter by movement type and export to CSV or
Excel.

## Locations

A fresh installation has Main stores (with bins A1 and A2), MSL dry cabinet 1, Production
WIP, Quarantine and Scrap.

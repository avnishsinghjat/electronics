# Procurement: from shortfall to goods received

FabTrack follows every BOQ line from "needed" to "in stores":

**BOQ shortfall → purchase requisition (PR) → purchase order (PO) → goods receipt (GRN) → stock**

## The tracker (project → Procurement tab)

The tracker lists every line of the project's BOQs (the released revision; a draft-only BOQ
shows with a warning) with:

- **Required**: quantity per unit × build quantity × (1 + attrition %), rounded up.
- **Ordered**: on issued, received or closed purchase orders.
- **Received**: accepted at goods receipt.
- **Issued**: issued to production (kitting, from Phase 7).
- **To order**: required − ordered.
- **Awaiting**: ordered − received.
- **On PR / draft PO**: already in purchasing, so it is not requisitioned twice.
- **Expected**, **Days late**, **Vendor**, **Purchase orders** (click to open), **Value
  pending** and the **Status** pill.

The status comes from one rule shared by every screen and report: Not required (DNP or
zero), Not ordered, Partially ordered, Ordered, Partially received, Received, Issued.

At the top:

- **Lines fully received**, **Lines to order**, **Awaiting delivery**, **Overdue lines**
  and **Value pending** (ordered, not yet received, at PO prices).
- **Clear to build**: one chip per module. It turns green only when every required line
  of the module's BOQ has been received in full. DNP and zero-quantity lines never block
  it. Hover a chip to see why it is not green.

Filter by status, vendor, module or **Overdue only**; group by vendor or category. Every
table exports to CSV or Excel (**Export**).

## Requisitions

1. On the tracker, select the lines you need (tick boxes) and click **Requisition
   selected**, or click **Requisition all shortfall**. Each line asks for what is still
   short and not already on another requisition or draft PO. Lines of an unreleased BOQ
   revision cannot be requisitioned: release them first.
2. On the requisition, check quantities and choose a **vendor** for every line (the
   part's preferred vendor is suggested), then **Save changes** and **Submit for
   approval**.
3. A Project Manager clicks **Approve**, or **Reject** with a reason. A rejected
   requisition can be edited and resubmitted.
4. Purchase clicks **Create purchase orders**: one draft PO per vendor. Each PO line is
   allocated to its BOQ line.

## Purchase orders

- **New purchase order** (Procurement page) creates an order directly. Each line can be
  **allocated** to one or more BOQ lines, even in different projects ("one reel for two
  projects"). Quantity left unallocated becomes free stock when received.
- Draft orders can be edited. Every line needs a unit price before **Issue to vendor**.
  Issued orders count as **ordered** on the tracker.
- **PDF** prints the order on your company letterhead (logo, address and GSTIN from
  Settings → General), with the vendor's details and terms.
- Follow-up: the calendar icon on a line records the vendor's new promised date and a
  note.
- **Cancel the remainder** of a line (ban icon) when the vendor cannot deliver the rest.
  What arrived stays; the rest shows as short again on the tracker, ready to reorder.
  **Cancel order** is only possible before anything is received.
- **Close order** marks it finished. Closed orders still count as ordered.

## Receiving goods (GRN)

On an issued order, click **Receive goods**. For each line that arrived, enter:

- **Received**, and split it: **Rejected** (with a reason) and **On hold** (waiting for an
  inspection decision). **Accepted** is what is left.
- **Location**: Stores by default; MSL-sensitive parts (MSL 2 and above) default to the
  MSL dry cabinet.
- **Lot / batch** and **date code**.

Only accepted quantity enters stock. It is reserved for the projects the line was
allocated to, oldest allocation first. Rejected quantity opens a **vendor return** and stays
outstanding on the PO, because the vendor owes a replacement. You cannot receive more
than is outstanding. If two people receive the same line at the same moment, the second
one is told how much is left.

On the GRN page:

- attach the vendor's **certificate of conformance** and photos of the packaging and
  labels, then mark which file is the CoC;
- click **Decide** on a line on hold to accept or reject that quantity.

## Pending deliveries and returns

**Procurement → Pending deliveries** lists every PO line still owed, across all projects,
soonest first, with days late. Purchase uses it for the daily follow-up calls.
**Vendor returns** tracks rejected goods: shipped, credited or replaced, then closed.

## Vendors

**Procurement → Vendors**: code, name, GSTIN (format-checked), address, contacts, payment
terms, lead time, rating and documents (attach the vendor's terms, certificates and
approvals). A vendor with purchase orders cannot be deleted.

## Who can do what

| Action | Roles |
| --- | --- |
| See procurement and the tracker | every internal role (not the client Viewer) |
| Raise and edit requisitions | Project Manager, Purchase, Admin |
| Approve requisitions | Project Manager, Admin |
| Create, issue, cancel and close POs; manage vendors | Purchase, Admin |
| Receive goods, decide holds, update returns | Stores, QC Inspector, Admin |

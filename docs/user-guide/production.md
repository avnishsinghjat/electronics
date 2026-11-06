# Production: work orders, kitting and the shop floor

One **work order** builds one PCB assembly as one **lot**. It goes through the stages of
the assembly's stage template (kitting, SMT, reflow, AOI… packing). Each board is tracked
by serial number, or the lot is tracked as a whole for low-value boards.

## Stage templates (Production → Stage templates)

- The **default** template has the twelve standard stages. Copy it (copy icon) to make
  your own, then **Edit**:
  - reorder stages with the arrows;
  - rename them, or add custom stages such as potting or burn-in;
  - tick **QC** on the stages that need a passed QC inspection before a board moves on.
- Choose the template for a board in the assembly's details on the project page. Boards
  without one use the default.
- A new work order copies the template's stages, so later template edits do not change
  orders already created.

## Work orders

1. **New work order** (Production page, or a project's Production tab): choose the PCB
   assembly. The build quantity defaults to the module's quantity to deliver.
   - FabTrack picks the BOQ to kit from: the board's own BOQ, else the module's.
   - Untick **Track each board by serial number** to track by lot only.
2. **Release to production** needs the module to be **clear to build**: every BOQ line
   received, as on the Procurement tracker.
   - If it is not, only a Project Manager can release it, and must give a reason.
   - The reason is shown on the work order and written to the audit log under their name.
3. The work order moves along the **board** (Production → Board) as stages complete:
   Planned → Released → the current stage → Completed. **Close** a completed order to
   take it off the board.

## Kitting (work order → Kitting)

- The kit list shows, for every BOQ line, what this order needs (quantity per board ×
  build quantity, plus attrition), what has been issued, what is still short, what is
  reserved for the project and what is in stock.
- **Issue** opens the lots in stock, oldest first, with the shortage already spread over
  them. Change the quantities if you pick from other lots.
  - Every issue is a stock movement (ledger ISSUE) against the BOQ line. It appears as
    **Issued** on the tracker and uses up the project's reservation.
  - You cannot issue more than the order needs, nor more than a lot holds at that
    location.
- **Return** sends unused parts back to stores (ledger RETURN), reserved for the project
  again. A work order cannot be cancelled while kitted parts are still out.
- Partial kitting is fine: issue what is in stores now, and the rest when it arrives.

## Serial numbers and labels (work order → Units and stages)

- **Generate serial numbers** creates one per board:
  `PREFIX-ASSEMBLY-YEAR-NNNNN`, e.g. `SN-CPU1-2026-00042`.
  - The prefix is set in Settings → General.
  - The running number continues per assembly and year and never repeats, even when
    two orders are serialised at the same moment.
- **Print labels (PDF)** makes an A4 sheet of 3 × 8 labels (70 × 37 mm). Each has a QR
  code of the serial, the board, the work order and the lot. Everything is generated on
  the server, offline.
- The branch icon on a unit shows its **genealogy**: the part lots kitted to its work
  order.

## Recording progress

- **Serial-tracked**: each unit has **Start** at its next stage, then **Pass** / **Fail**.
  - A unit can only start a stage after passing the previous one.
  - A failed unit stops; hand it to QC.
- **Lot-tracked**: start the current stage for the lot, then record how many **passed**
  and **failed**. Only the passed quantity moves on.
- **QC stages**: Pass/Fail sends the unit (or lot) to **Awaiting QC**. It is completed
  only when a QC inspection of that stage has passed.
  - **Check QC and complete** tries again.
  - Nobody can skip this, not even through the API.
  - QC inspections are recorded in the QC module (Phase 8).

## Shop-floor mode (tablets)

**Shop-floor mode** is a full-screen, large-button layout for tablets on the line.

- **Scan** a serial label:
  - **Camera**: reads the QR code on the tablet itself. It needs an HTTPS connection to
    the server; until HTTPS is set up, use a handheld scanner or type the serial.
  - **Handheld USB/Bluetooth scanner**: the serial box always has the focus, so a scan
    lands there.
  - **Type** the serial and press Enter.
- The unit's current stage appears with its next action (Start, Pass, Fail).
- **On the floor** lists the released work orders. Tap a serial to open it; lot-tracked
  orders show their current stage's controls directly.

## Who can do what

| Action | Roles |
| --- | --- |
| See production | every internal role (not the client Viewer) |
| Create and edit work orders, templates, serials | Project Manager, Production, Admin |
| Release when clear to build | Project Manager, Production, Admin |
| Release with an override reason | Project Manager, Admin |
| Issue and return kit | Stores, Production, Admin |
| Record stage progress | Production, Admin |

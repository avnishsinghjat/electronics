# Bills of quantity (BOQ)

A BOQ lists everything needed to build a project, a module, or one PCB assembly: reference
designators, quantity per unit, MPN, manufacturer, description, category and so on. FabTrack
keeps every BOQ in **revisions** (A, B, C…) so you can always see what the client sent and
what changed.

Open a project and choose the **BOQ** tab. The **BOQ** page in the sidebar lists every BOQ in
every project you can see, with its current revision. Click a project number to open it.

## Revisions

- A revision is either a **draft** (editable), **released** (the one purchasing and stores
  work from) or **superseded** (an older released revision, read-only).
- Only one revision is released at a time. Releasing revision B supersedes revision A.
- Only one draft can exist at a time. To change a released BOQ, click **New revision**. It
  starts as a copy of the current revision.
- Every line keeps a hidden **line key** across revisions. That is how compare knows a line
  was edited rather than removed and added again.

Who can do what: Project Managers, Engineers and Admins edit drafts and import files;
Project Managers and Admins release. Purchase, Stores, Production and QC can read BOQs. The
client Viewer cannot.

## Creating a BOQ

Click **New BOQ** and give it a name. Choose the module (the build quantity then defaults to
the module's quantity to deliver) and, optionally, the PCB assembly. Then either:

- **Start empty**: creates draft revision A for you to type or paste into; or
- **Create and import file**: opens the import wizard straight away.

## Typing and pasting (the grid)

A draft revision opens in a spreadsheet-like grid.

- **Enter** or **↓** moves down; **Shift+Enter** or **↑** moves up; **←/→** move between
  cells when the cursor is at the start or end of the text. **Enter on the last row adds a
  new row.**
- **Paste from Excel**: copy rows in Excel and paste into any cell. Columns are filled
  left to right from that cell, in the grid's column order (Ref des, Qty / unit, MPN,
  Manufacturer, Description, Value, Package, Category, Unit, DNP, Attrition %, Unit price,
  Notes). Extra rows are added as needed.
- **MPN suggestions**: type two or more characters of an MPN to see matching parts from the
  part master. Picking one links the line to that part and fills empty description,
  package, value and category cells. If the part does not exist yet, **Create part "…"** adds
  it to the part master (Project Managers, Engineers, Purchase and Admins).
- Leave **Attrition %** empty to use the category rate (see below). A number there overrides
  the category for that line.
- Click **Save lines**. If the server rejects a line (for example a negative quantity), the
  line is highlighted and the reason is listed above the grid.

## Build quantity and attrition

The **Build quantity and attrition** card holds the build quantity and an attrition
(spoilage) % for each category used in the revision, for example Passive 2 %, IC 0 %. New
revisions start from the company defaults.

FabTrack computes, for every line:

```
required = qty per unit × build quantity × (1 + attrition %)
```

The result is rounded **up** to whole units for countable units (pcs, nos…) and to 0.01 for
others (metres of wire, grams of paste). Example: 8 capacitors per board × 25 boards × 1.02 =
204. DNP lines (do not populate) need 0.

The **Status** column (Not ordered, Partially ordered, Ordered, Partially received,
Received, Issued) is computed by the server from purchase orders, goods receipts and kitting.
Until procurement goes live in Phase 6, every line correctly shows **Not ordered** and
**To order** equals **Required**.

## Importing a file (the wizard)

Click **Import file** (you need a BOQ selected). Nothing is saved until the last step.

1. **Upload**: CSV, TSV, TXT, XLSX or a KiCad BOM export (`kicad-cli sch export bom`).
   FabTrack detects the encoding (UTF-8, UTF-8 with BOM, Windows-1252), the delimiter
   (comma, semicolon, tab, pipe) and the header row, even with title rows above it.
2. **Map columns**: each FabTrack field shows the column FabTrack matched and the first
   values from your file. Change any mapping with the dropdowns, or pick a different
   header row. Tick **Numbers use a decimal comma** for European files (`1,5`). Tick **Save
   this mapping** to reuse it: next time a file from the same client arrives with the same
   headings, the mapping is applied automatically, or choose it under **Saved mapping**.
3. **Check**: every row is validated. Lines with the same MPN, manufacturer and DNP state are
   merged and their ref des combined. Errors block the commit. Fix them in the file, or in
   the mapping if a column was mapped wrongly, then upload again. **Error report CSV**
   downloads every row with its problems, to send back to the client.
4. **Commit**: creates a new revision: it fills an empty draft, or becomes the next letter.
   Optionally set the build quantity and release it immediately. MPNs not in the part master
   are added to it, marked "Created by BOQ import".

### What the check finds

| Code | Severity | Meaning |
| --- | --- | --- |
| `missing_mpn` | Error | No MPN, and the line is not DNP |
| `invalid_qty` | Error | Quantity is not a number, or is negative |
| `missing_qty` | Error | No quantity and no ref des to count |
| `qty_ref_des_mismatch` | Error | Quantity differs from the number of ref des (countable units only) |
| `duplicate_ref_des` | Error | The same designator appears on two rows |
| `mapping_incomplete` | Error | MPN (or description) column, or quantity/ref des column, is not mapped |
| `no_rows` | Error | No data rows under the header |
| `unknown_part` | Warning | MPN not in the part master; it will be created on commit |
| `mpn_variant_master` | Warning | MPN matches a part master entry except for case, spaces or dashes; the master spelling is used |
| `mpn_variant` | Warning | Two rows differ only in MPN case/spacing; they are merged |
| `qty_from_ref_des` | Warning | No quantity given; the ref des count is used |
| `invalid_price` | Warning | Unit price is not a number; it is ignored |
| `merged` | Info | Row merged into an earlier line with the same MPN |

Ranges such as `R1-R4` are expanded to R1, R2, R3, R4 before counting.

The `samples/` folder of the installation has example files: a clean BOQ, revision B of it,
a messy file with every problem above, a semicolon/decimal-comma European export, a KiCad
BOM and a 2,000-line file. The fresh-install sample data includes **PLC CPU board BOM
(Sample)** with revisions A and B.

## Comparing revisions

Click **Compare** (shown when a BOQ has two or more revisions) and pick the two revisions.
Lines are colour-coded:

- **Added** (green) and **Removed** (red);
- **Qty changed** (amber): the quantity per unit changed;
- **Part substituted** (blue): same line, different MPN;
- **Edited** (grey): other fields changed; **Changed fields** lists them.

Unchanged lines are hidden by default; **Show unchanged lines too** shows them. **Export**
saves the table as CSV or XLSX for the client or for purchasing.

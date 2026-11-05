# Projects, modules and PCB assemblies

Every piece of work in FabTrack hangs off this structure:

**Division → Project → Module → PCB assembly**

- A **division** is a business unit (e.g. Industrial Automation).
- A **project** is one client order. Its number (e.g. `PRJ-2026-0004`) is assigned
  automatically.
- A **module** is a deliverable unit of the project, with the quantity to deliver (e.g.
  "Controller module × 50").
- A **PCB assembly** is a board revision used in a module (code, revision, layers, size,
  finish, production stage list, drawing and KiCad project).

## Finding projects (Projects)

Projects are grouped by division. Filter by status (open projects by default), project
manager, client and due window (overdue, next 30 or 90 days). The **division switcher** in
the top bar limits the list (and later the dashboards) to one division; FabTrack remembers
it on this computer. **Jump to project** in the top bar finds any project by number, name or
client.

## Creating and editing

- **New project** (Project Managers and Admins): name, client, client PO reference,
  division, status, start and due dates, project manager, notes.
- On the project page: **Add module**, then **+ Assembly** inside a module. Edit or delete
  with the pencil and bin icons. Delete children first: a module with assemblies, or a
  project with modules, cannot be deleted.
- If someone else saved the same record meanwhile, you get a "changed by someone else"
  message. Reload and redo your change.

## Files

Drag files onto the **Files** tab of a project, or onto the files area inside an assembly.
Images and PDFs can be previewed, everything can be downloaded, and deletions are recorded.
For an assembly, attach the drawing and the zipped KiCad project, then choose them in the
**Assembly drawing** and **KiCad project** fields.

## Repeat orders: Clone

**Clone** copies the modules and PCB assemblies (including the drawing and KiCad file links)
into a new draft project with a new number. Tick **Copy the current revision of each BOQ** to
bring the BOQs along as draft revision A. Purchase orders, stock, production and QC records
are never copied.

## History

The **History** tab lists every change to the project, its modules, assemblies and files,
with who made it and when.

## Tabs that appear later

The **BOQ** tab holds the project's bills of quantity: see [BOQ](boq.md). Procurement,
Production, QC and Documents tabs appear as their modules go live (Phases 6 to 11).

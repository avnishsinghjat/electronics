# Getting around FabTrack

## The layout

- **Sidebar (left)**: every section of FabTrack. The highlighted entry is the page you are
  on. **Collapse** (bottom of the sidebar) shrinks it to icons; hover an icon to see its
  name. FabTrack remembers the choice on this computer.
- **Top bar**: the search box and the AI status badge.
- **Page header**: a breadcrumb (where you are), the page title, and the page's main action
  on the right.

## Jump anywhere with Ctrl+K

Press **Ctrl+K** (or click the search box) to open the command palette. Type part of a page
name, use the arrow keys, press **Enter**. Searching parts, purchase orders, serials and NCRs
from the palette arrives with the dashboards in Phase 13.

## AI status badge

| Badge | Meaning |
| --- | --- |
| Green dot, "AI local" | A local model (LM Studio or an in-house server) is connected. |
| Blue dot, "AI online" | An online provider (OpenRouter) is in use; only possible when air-gapped mode is off. |
| Grey dot, "AI off" | No AI provider is configured or reachable. Everything except AI drafting still works. |

Hover the badge for the detail.

## Status colours

The same colours mean the same thing everywhere:

| Colour | Meaning |
| --- | --- |
| Grey | Not started |
| Blue | In progress |
| Amber | Pending or at risk |
| Green | Done or passed |
| Red | Failed or blocked |

## Tables

Every table has the same tools:

- **Search** filters across all columns; the small **Filter** boxes under each header filter
  one column.
- Click a column header to sort; click again to reverse.
- **Columns** shows or hides columns and pins a column to the left so it stays visible while
  you scroll sideways.
- **Save view** (bookmark icon) stores the current sorting, filters and columns under a name
  in this browser; pick it again from the view list.
- **Export** downloads exactly the rows that match your filters, in the current order, as
  CSV (opens in Excel with ₹ and µ intact) or XLSX.
- Large tables (thousands of rows) scroll smoothly; printing a table prints every row.

## Sections not live yet

Sections whose module has not been delivered show which phase delivers them. They contain no
mock-ups or dummy data.

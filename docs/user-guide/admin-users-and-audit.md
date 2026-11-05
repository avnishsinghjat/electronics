# Administration: first-run setup, users and the audit log

## First-run setup (once per server)

On a new installation FabTrack opens the setup wizard:

1. **Data directory**: confirms the folder for photos, documents and KiCad files exists, is
   writable and has at least 1 GiB free.
2. **Company and administrator**: company name and the first administrator account.
3. **Document numbers**: prefixes such as `PO` in `PO-2026-0001`. Numbers are gap-free and
   restart every year.
4. **Logo** (optional): PNG, JPEG or WebP up to 2 MB.

The wizard can only run while no user exists.

## Users (Settings → Users)

- **New user**: username, full name, one or more roles, and optional restrictions to
  divisions or projects. FabTrack shows a temporary password **once**; hand it over in
  person. The user must replace it at first sign-in.
- **Edit**: change name, email, roles and restrictions. If someone else saved the same user
  meanwhile you get a "changed by someone else" message: reload and redo the change.
- **Reset password**: new temporary password, unlocks the account, signs the user out
  everywhere.
- **Deactivate**: the user is signed out at once and cannot sign in; their history stays.
  You cannot deactivate yourself, and the last active administrator cannot be removed.

### Roles

| Role | Typical use |
| --- | --- |
| Admin | Everything, including users and settings |
| Project Manager | Projects, BOQs, requisition approval, work order release |
| Purchase | Vendors, purchase orders |
| Stores | Goods receipt, stock transfers, kitting |
| Production | Work orders and shop-floor progress |
| QC Inspector | Inspections, photo evidence, NCRs, report review |
| QC Lead | QC templates, NCR closure, report approval |
| Engineer | KiCad Design Lab, design sign-off |
| Viewer (client) | Read-only: projects in scope and issued QC reports |

## Audit log (Settings → Audit log)

Every change to business records, plus sign-ins, failed sign-ins, lockouts and sign-outs.
Filter by user, record type, action and dates. **View** opens the before/after of each field;
changed fields are highlighted and listed first. Passwords never appear (shown as
`[redacted]`).

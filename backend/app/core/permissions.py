"""Roles and the permission matrix: the single definition of who may do what.

Routers declare a permission on every endpoint with ``Depends(require("perm"))`` (or
``Depends(public)`` for the few anonymous endpoints); services re-check with
``user.require(...)`` and apply project/division scoping. A test fails if any route
declares neither.
"""

import enum


class Role(enum.StrEnum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    PURCHASE = "purchase"
    STORES = "stores"
    PRODUCTION = "production"
    QC_INSPECTOR = "qc_inspector"
    QC_LEAD = "qc_lead"
    ENGINEER = "engineer"
    VIEWER = "viewer"


ROLE_LABELS: dict[Role, str] = {
    Role.ADMIN: "Admin",
    Role.PROJECT_MANAGER: "Project Manager",
    Role.PURCHASE: "Purchase",
    Role.STORES: "Stores",
    Role.PRODUCTION: "Production",
    Role.QC_INSPECTOR: "QC Inspector",
    Role.QC_LEAD: "QC Lead",
    Role.ENGINEER: "Engineer",
    Role.VIEWER: "Viewer (client)",
}

# Every permission string, with a description shown in the admin UI and gate report.
PERMISSIONS: dict[str, str] = {
    # administration
    "users:read": "View users",
    "users:manage": "Create, edit, deactivate users; reset passwords; assign roles and scopes",
    "audit:read": "View the audit log",
    "settings:read": "View company settings and document numbering",
    "settings:manage": "Change company settings, logo and document numbering",
    # structure
    "divisions:read": "View divisions",
    "divisions:manage": "Create and edit divisions",
    "projects:read": "View projects, modules and assemblies (within scope)",
    "projects:manage": "Create, edit, clone projects, modules and assemblies",
    "projects:history": "View a project's change history",
    "directory:read": "See staff names in pickers (project manager, inspector, ...)",
    "files:upload": "Attach files to records",
    "files:delete": "Delete attached files",
    # BOQ and parts
    "boq:read": "View BOQs and revisions",
    "boq:edit": "Edit BOQ lines",
    "boq:import": "Import BOQ CSV/XLSX",
    "boq:release": "Release a BOQ revision",
    "parts:read": "View the part master",
    "parts:manage": "Create and edit parts",
    # procurement and stores
    "procurement:read": "View vendors, requisitions, POs, GRNs and the tracker",
    "vendors:manage": "Create and edit vendors",
    "pr:create": "Raise purchase requisitions",
    "pr:approve": "Approve purchase requisitions",
    "po:manage": "Create, issue, cancel purchase orders",
    "grn:create": "Receive goods (GRN) and record incoming inspection",
    "inventory:read": "View stock and the ledger",
    "inventory:transfer": "Transfer stock between locations",
    "inventory:adjust": "Request stock adjustments",
    "inventory:approve_adjustment": "Approve stock adjustments",
    # production
    "production:read": "View work orders and stage progress",
    "wo:manage": "Create and plan work orders",
    "wo:release": "Release work orders that are clear to build",
    "wo:override_release": "Release a work order that is not clear to build (with reason)",
    "kitting:issue": "Issue and return kit parts",
    "stage:progress": "Record stage progress on the shop floor",
    # QC
    "qc:read": "View inspections, NCRs and evidence",
    "qc:inspect": "Perform QC inspections and upload evidence",
    "qc:manage_templates": "Create and version QC templates",
    "ncr:raise": "Raise NCRs",
    "ncr:close": "Disposition and close NCRs",
    # reports and documents
    "reports:read": "View QC reports in all states",
    "reports:read_issued": "View issued, client-safe QC reports",
    "reports:create": "Generate and edit QC report drafts",
    "reports:review": "Mark QC reports reviewed",
    "reports:approve": "Approve and issue QC reports (e-signature)",
    "documents:read": "View document drafts",
    "documents:draft": "Draft documents with the LLM",
    "documents:approve": "Approve documents",
    # design lab and AI
    "design:read": "View design evaluations",
    "design:run": "Upload KiCad projects and run checks/simulations",
    "design:signoff": "Sign off a design revision for production",
    "llm:use": "Use AI drafting features",
    "llm:manage": "Configure AI providers, models and prompts",
    # dashboards
    "dashboard:read": "View dashboards",
}

_READ_ALL = {
    "projects:history",
    "directory:read",
    "divisions:read",
    "projects:read",
    "boq:read",
    "parts:read",
    "procurement:read",
    "inventory:read",
    "production:read",
    "qc:read",
    "reports:read",
    "documents:read",
    "design:read",
    "dashboard:read",
}

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMIN: frozenset(PERMISSIONS),
    Role.PROJECT_MANAGER: frozenset(
        _READ_ALL
        | {
            "projects:manage",
            "divisions:manage",
            "files:upload",
            "files:delete",
            "boq:edit",
            "boq:import",
            "boq:release",
            "parts:manage",
            "pr:create",
            "pr:approve",
            "wo:manage",
            "wo:release",
            "wo:override_release",
            "reports:create",
            "documents:draft",
            "llm:use",
            "settings:read",
            "users:read",
        }
    ),
    Role.PURCHASE: frozenset(
        _READ_ALL
        | {
            "vendors:manage",
            "pr:create",
            "po:manage",
            "parts:manage",
            "files:upload",
            "documents:draft",
            "llm:use",
        }
    ),
    Role.STORES: frozenset(
        _READ_ALL
        | {
            "grn:create",
            "inventory:transfer",
            "inventory:adjust",
            "kitting:issue",
            "files:upload",
        }
    ),
    Role.PRODUCTION: frozenset(
        _READ_ALL | {"wo:manage", "wo:release", "kitting:issue", "stage:progress", "files:upload"}
    ),
    Role.QC_INSPECTOR: frozenset(
        _READ_ALL
        | {
            "qc:inspect",
            "ncr:raise",
            "grn:create",
            "files:upload",
            "reports:create",
            "reports:review",
            "documents:draft",
            "llm:use",
        }
    ),
    Role.QC_LEAD: frozenset(
        _READ_ALL
        | {
            "qc:inspect",
            "qc:manage_templates",
            "ncr:raise",
            "ncr:close",
            "files:upload",
            "reports:create",
            "reports:review",
            "reports:approve",
            "documents:draft",
            "documents:approve",
            "inventory:approve_adjustment",
            "llm:use",
        }
    ),
    Role.ENGINEER: frozenset(
        _READ_ALL
        | {
            "design:run",
            "design:signoff",
            "boq:edit",
            "boq:import",
            "parts:manage",
            "files:upload",
            "documents:draft",
            "llm:use",
        }
    ),
    # Client-safe read-only: projects in scope and issued reports only.
    Role.VIEWER: frozenset({"projects:read", "reports:read_issued"}),
}


def permissions_for(roles: list[Role] | set[Role] | frozenset[Role]) -> frozenset[str]:
    perms: set[str] = set()
    for role in roles:
        perms |= ROLE_PERMISSIONS[role]
    return frozenset(perms)


def _check_matrix() -> None:
    unknown = {p for perms in ROLE_PERMISSIONS.values() for p in perms} - set(PERMISSIONS)
    if unknown:
        raise RuntimeError(f"Unknown permissions in role matrix: {sorted(unknown)}")


_check_matrix()

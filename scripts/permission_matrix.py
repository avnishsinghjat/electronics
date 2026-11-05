"""Print the role x permission matrix as a Markdown table (source: app/core/permissions.py).

Usage: backend/.venv/bin/python scripts/permission_matrix.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.permissions import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS, Role  # noqa: E402

SHORT = {
    Role.ADMIN: "Admin",
    Role.PROJECT_MANAGER: "PM",
    Role.PURCHASE: "Purch",
    Role.STORES: "Stores",
    Role.PRODUCTION: "Prod",
    Role.QC_INSPECTOR: "QC Insp",
    Role.QC_LEAD: "QC Lead",
    Role.ENGINEER: "Eng",
    Role.VIEWER: "Viewer",
}


def render() -> str:
    roles = list(Role)
    lines = [
        "| Permission | Meaning | " + " | ".join(SHORT[r] for r in roles) + " |",
        "| --- | --- | " + " | ".join(":-:" for _ in roles) + " |",
    ]
    for perm, desc in PERMISSIONS.items():
        cells = ["✓" if perm in ROLE_PERMISSIONS[r] else "" for r in roles]
        lines.append(f"| `{perm}` | {desc} | " + " | ".join(cells) + " |")
    legend = ", ".join(f"{SHORT[r]} = {ROLE_LABELS[r]}" for r in roles)
    return "\n".join(lines) + f"\n\nColumns: {legend}."


if __name__ == "__main__":
    print(render())

"""Print a Mermaid ER diagram of every table, generated from the SQLAlchemy metadata.

Usage: backend/.venv/bin/python scripts/er_diagram.py > docs/api/er-diagram.md
The gate report embeds the same output, so the diagram cannot drift from the models.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import Column  # noqa: E402

from app.models import Base  # noqa: E402

MIXIN = {"created_at", "updated_at", "created_by", "updated_by", "is_deleted", "row_version"}


def _type(col: Column) -> str:  # type: ignore[type-arg]
    name = type(col.type).__name__.lower()
    return {"uuid": "uuid", "numeric": "numeric", "datetime": "timestamptz"}.get(name, name)


def render() -> str:
    lines = ["erDiagram"]
    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        cols = [c for c in table.columns if c.name not in MIXIN]
        lines.append(f"    {table.name} {{")
        for col in cols:
            keys = []
            if col.primary_key:
                keys.append("PK")
            if col.foreign_keys:
                keys.append("FK")
            suffix = f" {','.join(keys)}" if keys else ""
            lines.append(f"        {_type(col)} {col.name}{suffix}")
        lines.append("    }")
    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        for fk in sorted(table.foreign_keys, key=lambda f: f.parent.name):
            target = fk.column.table.name
            card = "|o--o{" if fk.parent.nullable else "||--o{"
            lines.append(f'    {target} {card} {table.name} : "{fk.parent.name}"')
    return "\n".join(lines)


if __name__ == "__main__":
    print("```mermaid")
    print(render())
    print("```")

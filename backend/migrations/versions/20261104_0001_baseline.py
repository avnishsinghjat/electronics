"""Baseline revision: establishes the migration chain. Domain tables arrive in Phase 1.

Revision ID: 0001
Revises:
Create Date: 2026-11-04
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to create yet; the alembic_version row marks the database as managed."""


def downgrade() -> None:
    """Nothing to drop."""

"""Persist the operational creator display name on resource requirements.

Revision ID: 0009_requirement_creator_name
Revises: 0008_command_idempotency
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0009_requirement_creator_name"
down_revision: str | None = "0008_command_idempotency"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "resource_requirements",
        sa.Column("created_by_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resource_requirements", "created_by_name")

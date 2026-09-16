"""Add durable business audit for segments and manual shifts.

Revision ID: 0015_planning_change_history
Revises: 0014_m365_draft_audit
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0015_planning_change_history"
down_revision: str | None = "0014_m365_draft_audit"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "planning_change_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("entity_reference", sa.String(length=128), nullable=False),
        sa.Column("parent_reference", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planning_change_history")),
    )
    op.create_index(
        "ix_planning_change_history_entity_time",
        "planning_change_history",
        ["entity_type", "entity_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_planning_change_history_reference_time",
        "planning_change_history",
        ["entity_type", "entity_reference", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planning_change_history_reference_time",
        table_name="planning_change_history",
    )
    op.drop_index(
        "ix_planning_change_history_entity_time",
        table_name="planning_change_history",
    )
    op.drop_table("planning_change_history")

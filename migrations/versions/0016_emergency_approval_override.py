"""Add auditable emergency approval override state.

Revision ID: 0016_emergency_approval_override
Revises: 0015_planning_change_history
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0016_emergency_approval_override"
down_revision: str | None = "0015_planning_change_history"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "workforce_requests",
        sa.Column(
            "emergency_override_active",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "workforce_requests",
        sa.Column("emergency_override_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "workforce_requests",
        sa.Column("emergency_override_by_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "workforce_requests",
        sa.Column("emergency_override_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_workforce_requests_emergency_override_active"),
        "workforce_requests",
        ["emergency_override_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workforce_requests_emergency_override_active"),
        table_name="workforce_requests",
    )
    op.drop_column("workforce_requests", "emergency_override_at")
    op.drop_column("workforce_requests", "emergency_override_by_name")
    op.drop_column("workforce_requests", "emergency_override_reason")
    op.drop_column("workforce_requests", "emergency_override_active")

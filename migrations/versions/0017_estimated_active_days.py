"""Add desired active-day targets to periods and materialized requirements.

Revision ID: 0017_estimated_active_days
Revises: 0016_emergency_approval_override
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0017_estimated_active_days"
down_revision: str | None = "0016_emergency_approval_override"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "workforce_request_periods",
        sa.Column("desired_active_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "resource_requirements",
        sa.Column("desired_active_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resource_requirements", "desired_active_days")
    op.drop_column("workforce_request_periods", "desired_active_days")

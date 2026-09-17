"""Add load profiles to materialized resource requirements.

Revision ID: 0018_load_profiles
Revises: 0017_estimated_active_days
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0018_load_profiles"
down_revision: str | None = "0017_estimated_active_days"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "resource_requirements",
        sa.Column(
            "load_profile",
            sa.String(length=32),
            nullable=False,
            server_default="UNIFORM",
        ),
    )


def downgrade() -> None:
    op.drop_column("resource_requirements", "load_profile")

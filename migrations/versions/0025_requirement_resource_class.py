"""Snapshot RequestLine resource class on materialized requirements.

Revision ID: 0025_requirement_resource_class
Revises: 0024_line_scoped_periods
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0025_requirement_resource_class"
down_revision: str | None = "0024_line_scoped_periods"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.add_column(
            sa.Column("required_resource_class", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            "ix_req_required_resource_class",
            ["required_resource_class"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.drop_index("ix_req_required_resource_class")
        batch_op.drop_column("required_resource_class")

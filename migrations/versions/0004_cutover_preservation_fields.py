"""Preserve legacy resource and audit fields during the Excel cutover.

Revision ID: 0004_cutover_preservation_fields
Revises: 0003_global_holiday_availability
Create Date: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_cutover_preservation_fields"
down_revision: Union[str, Sequence[str], None] = "0003_global_holiday_availability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("competencies", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("note", sa.Text(), nullable=True))
    op.add_column(
        "workforce_request_history",
        sa.Column("previous_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "workforce_request_history",
        sa.Column("details", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workforce_request_history", "details")
    op.drop_column("workforce_request_history", "previous_status")
    op.drop_column("resources", "note")
    op.drop_column("resources", "competencies")

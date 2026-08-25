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
    with op.batch_alter_table("resources") as batch:
        batch.add_column(sa.Column("competencies", sa.Text(), nullable=True))
        batch.add_column(sa.Column("note", sa.Text(), nullable=True))
    with op.batch_alter_table("workforce_request_history") as batch:
        batch.add_column(sa.Column("previous_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("details", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workforce_request_history") as batch:
        batch.drop_column("details")
        batch.drop_column("previous_status")
    with op.batch_alter_table("resources") as batch:
        batch.drop_column("note")
        batch.drop_column("competencies")

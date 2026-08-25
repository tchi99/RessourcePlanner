"""Allow global holiday availability rules.

Revision ID: 0003_global_holiday_availability
Revises: 0002_unique_business_ids
Create Date: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_global_holiday_availability"
down_revision: Union[str, Sequence[str], None] = "0002_unique_business_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_availability_rules") as batch:
        batch.alter_column(
            "resource_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.create_check_constraint(
            op.f("ck_resource_availability_rules_availability_resource_or_global_holiday"),
            "resource_id IS NOT NULL OR availability_type = 'Jour férié'",
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_availability_rules") as batch:
        batch.drop_constraint(
            op.f("ck_resource_availability_rules_availability_resource_or_global_holiday"),
            type_="check",
        )
        batch.alter_column(
            "resource_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

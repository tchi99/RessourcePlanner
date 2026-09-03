"""link generated requirements to approved request period versions

Revision ID: 0006_request_period_requirement_links
Revises: 0005_request_period_alternatives
Create Date: 2026-09-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_request_period_requirement_links"
down_revision: Union[str, Sequence[str], None] = "0005_request_period_alternatives"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "workforce_request_period_requirements",
        sa.Column("resource_requirement_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("period_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.ForeignKeyConstraint(["period_id"], ["workforce_request_periods.id"]),
        sa.ForeignKeyConstraint(["resource_requirement_id"], ["resource_requirements.id"]),
        sa.PrimaryKeyConstraint("resource_requirement_id"),
    )
    op.create_index(
        "ix_request_period_requirement_period",
        "workforce_request_period_requirements",
        ["period_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_request_period_requirement_period",
        table_name="workforce_request_period_requirements",
    )
    op.drop_table("workforce_request_period_requirements")

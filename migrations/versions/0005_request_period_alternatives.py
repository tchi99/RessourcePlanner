"""request periods and exclusive alternative selections

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "workforce_request_periods",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("sequence", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("kind", sa.String(length=32), server_default=sa.text("'CUMULATIVE'"), nullable=False),
        sa.Column("alternative_group", sa.String(length=64), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(12, 2), nullable=False),
        sa.Column("confirmation", sa.String(length=32), server_default=sa.text("'Tentative'"), nullable=False),
        sa.Column("proposed_resource_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("resource_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="request_period_date_window"),
        sa.CheckConstraint("hours > 0", name="request_period_hours_positive"),
        sa.CheckConstraint("resource_count >= 1", name="request_period_resource_count"),
        sa.CheckConstraint(
            "(kind = 'ALTERNATIVE' AND alternative_group IS NOT NULL) OR "
            "(kind = 'CUMULATIVE' AND alternative_group IS NULL)",
            name="request_period_kind_group_consistency",
        ),
        sa.ForeignKeyConstraint(["proposed_resource_id"], ["resources.id"]),
        sa.ForeignKeyConstraint(["workforce_request_id"], ["workforce_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_request_periods_request_kind_group",
        "workforce_request_periods",
        ["workforce_request_id", "kind", "alternative_group"],
        unique=False,
    )
    op.create_index(
        "ix_request_periods_request_active",
        "workforce_request_periods",
        ["workforce_request_id", "active"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_workforce_request_id",
        "workforce_request_periods",
        ["workforce_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_kind",
        "workforce_request_periods",
        ["kind"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_alternative_group",
        "workforce_request_periods",
        ["alternative_group"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_start_date",
        "workforce_request_periods",
        ["start_date"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_end_date",
        "workforce_request_periods",
        ["end_date"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_confirmation",
        "workforce_request_periods",
        ["confirmation"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_proposed_resource_id",
        "workforce_request_periods",
        ["proposed_resource_id"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_periods_active",
        "workforce_request_periods",
        ["active"],
        unique=False,
    )

    op.create_table(
        "workforce_request_period_selections",
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("alternative_group", sa.String(length=64), nullable=False),
        sa.Column("period_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_by_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["period_id"], ["workforce_request_periods.id"]),
        sa.ForeignKeyConstraint(["workforce_request_id"], ["workforce_requests.id"]),
        sa.PrimaryKeyConstraint("workforce_request_id", "alternative_group"),
    )
    op.create_index(
        "ix_request_period_selection_period",
        "workforce_request_period_selections",
        ["period_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_request_period_selection_period",
        table_name="workforce_request_period_selections",
    )
    op.drop_table("workforce_request_period_selections")

    for index_name in (
        "ix_workforce_request_periods_active",
        "ix_workforce_request_periods_proposed_resource_id",
        "ix_workforce_request_periods_confirmation",
        "ix_workforce_request_periods_end_date",
        "ix_workforce_request_periods_start_date",
        "ix_workforce_request_periods_alternative_group",
        "ix_workforce_request_periods_kind",
        "ix_workforce_request_periods_workforce_request_id",
        "ix_request_periods_request_active",
        "ix_request_periods_request_kind_group",
    ):
        op.drop_index(index_name, table_name="workforce_request_periods")
    op.drop_table("workforce_request_periods")

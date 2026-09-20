"""Scope alternative period selections by RequestLine.

Revision ID: 0024_line_scoped_periods
Revises: 0023_request_line_writes
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0024_line_scoped_periods"
down_revision: str | None = "0023_request_line_writes"
branch_labels: str | None = None
depends_on: str | None = None

ID_LENGTH = 36
_TEMP_TABLE = "workforce_request_period_selections_288d"


def _create_line_scoped_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("request_line_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("alternative_group", sa.String(length=64), nullable=False),
        sa.Column("period_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_by_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_period_sel_request",
        ),
        sa.ForeignKeyConstraint(
            ["request_line_id"],
            ["request_lines.id"],
            name="fk_period_sel_line",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["workforce_request_periods.id"],
            name="fk_period_sel_period",
        ),
        sa.PrimaryKeyConstraint(
            "request_line_id",
            "alternative_group",
            name="pk_workforce_request_period_selections",
        ),
    )


def _create_legacy_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("request_line_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("alternative_group", sa.String(length=64), nullable=False),
        sa.Column("period_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_by_name", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_period_sel_request",
        ),
        sa.ForeignKeyConstraint(
            ["request_line_id"],
            ["request_lines.id"],
            name="fk_period_sel_line",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["workforce_request_periods.id"],
            name="fk_period_sel_period",
        ),
        sa.PrimaryKeyConstraint(
            "workforce_request_id",
            "alternative_group",
            name="pk_workforce_request_period_selections",
        ),
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_request_period_selection_period",
        "workforce_request_period_selections",
        ["period_id"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_period_selections_workforce_request_id",
        "workforce_request_period_selections",
        ["workforce_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_workforce_request_period_selections_request_line_id",
        "workforce_request_period_selections",
        ["request_line_id"],
        unique=False,
    )


def upgrade() -> None:
    # 288B backfilled the deterministic legacy shadow line with id=request id.
    op.execute(
        sa.text(
            """
            UPDATE workforce_request_period_selections
            SET request_line_id = workforce_request_id
            WHERE request_line_id IS NULL
            """
        )
    )

    _create_line_scoped_table(_TEMP_TABLE)
    op.execute(
        sa.text(
            f"""
            INSERT INTO {_TEMP_TABLE} (
                workforce_request_id,
                request_line_id,
                alternative_group,
                period_id,
                selected_at,
                selected_by_name
            )
            SELECT
                workforce_request_id,
                request_line_id,
                alternative_group,
                period_id,
                selected_at,
                selected_by_name
            FROM workforce_request_period_selections
            """
        )
    )
    op.drop_table("workforce_request_period_selections")
    op.rename_table(_TEMP_TABLE, "workforce_request_period_selections")
    _create_indexes()


def downgrade() -> None:
    legacy = "workforce_request_period_selections_legacy"
    _create_legacy_table(legacy)

    # A legacy request could only retain one selection for a given group. When a
    # line-scoped request contains the same group name on several lines, collapse
    # deterministically during downgrade.
    op.execute(
        sa.text(
            f"""
            INSERT INTO {legacy} (
                workforce_request_id,
                request_line_id,
                alternative_group,
                period_id,
                selected_at,
                selected_by_name
            )
            SELECT
                workforce_request_id,
                MIN(request_line_id),
                alternative_group,
                MIN(period_id),
                MAX(selected_at),
                MAX(selected_by_name)
            FROM workforce_request_period_selections
            GROUP BY workforce_request_id, alternative_group
            """
        )
    )
    op.drop_table("workforce_request_period_selections")
    op.rename_table(legacy, "workforce_request_period_selections")
    _create_indexes()

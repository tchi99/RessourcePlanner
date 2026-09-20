"""Add request aggregate version and line-hours provenance.

Revision ID: 0023_request_line_writes
Revises: 0022_request_lines
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0023_request_line_writes"
down_revision: str | None = "0022_request_lines"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "aggregate_version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "line_mode",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.create_index(
            "ix_workforce_requests_line_mode",
            ["line_mode"],
            unique=False,
        )

    with op.batch_alter_table("request_lines") as batch_op:
        batch_op.add_column(
            sa.Column("estimated_hours_source", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("default_hours_per_day", sa.Numeric(12, 2), nullable=True)
        )

    op.execute(
        sa.text(
            """
            UPDATE request_lines
            SET estimated_hours_source = 'LEGACY'
            WHERE estimated_hours IS NOT NULL
              AND estimated_hours_source IS NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("request_lines") as batch_op:
        batch_op.drop_column("default_hours_per_day")
        batch_op.drop_column("estimated_hours_source")

    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.drop_index("ix_workforce_requests_line_mode")
        batch_op.drop_column("line_mode")
        batch_op.drop_column("aggregate_version")

"""Add operational budget overrides tied to approved request revisions.

Revision ID: 0033_request_operational_budgets
Revises: 0032_request_operational_choices
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0033_request_operational_budgets"
down_revision: str | None = "0032_request_operational_choices"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "request_operational_states",
        sa.Column(
            "budget_overrides_text",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("request_operational_states", "budget_overrides_text")

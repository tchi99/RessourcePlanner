"""persist requirement confirmation inheritance state

Revision ID: 0007_requirement_confirmation
Revises: 0006_request_period_requirement_links
Create Date: 2026-09-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007_requirement_confirmation"
down_revision: Union[str, Sequence[str], None] = "0006_request_period_requirement_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resource_requirements",
        sa.Column(
            "confirmation",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'Confirmée'"),
        ),
    )
    op.add_column(
        "resource_requirements",
        sa.Column(
            "confirmation_overridden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_resource_requirements_confirmation",
        "resource_requirements",
        ["confirmation"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_requirements_confirmation",
        table_name="resource_requirements",
    )
    op.drop_column("resource_requirements", "confirmation_overridden")
    op.drop_column("resource_requirements", "confirmation")

"""persist API command idempotency receipts

Revision ID: 0008_command_idempotency
Revises: 0007_requirement_confirmation
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_command_idempotency"
down_revision: Union[str, Sequence[str], None] = "0007_requirement_confirmation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "command_idempotency_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("command_scope", sa.String(length=96), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_command_idempotency_receipts"),
        sa.UniqueConstraint(
            "actor_name",
            "command_scope",
            "idempotency_key",
            name="uq_command_idempotency_actor_scope_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_receipts")

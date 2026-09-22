"""Add the singleton global planning mutation revision.

Revision ID: 0035_global_planning_version
Revises: 0034_canonical_requester_identity
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0035_global_planning_version"
down_revision: str | None = "0034_canonical_requester_identity"
branch_labels: str | None = None
depends_on: str | None = None

PLANNING_STATE_ID = "GLOBAL"


def upgrade() -> None:
    table = op.create_table(
        "planning_mutation_state",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint("id = 'GLOBAL'", name="planning_mutation_state_singleton"),
        sa.CheckConstraint("version >= 1", name="planning_mutation_state_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(table, [{"id": PLANNING_STATE_ID, "version": 1}])


def downgrade() -> None:
    op.drop_table("planning_mutation_state")

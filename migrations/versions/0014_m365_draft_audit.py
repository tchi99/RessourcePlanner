"""Audit Microsoft 365 draft creation for communication batches.

Revision ID: 0014_m365_draft_audit
Revises: 0013_web_communications
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0014_m365_draft_audit"
down_revision: str | None = "0013_web_communications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "communication_batches",
        sa.Column("drafts_provider", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "communication_batches",
        sa.Column("drafts_created_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "communication_batches",
        sa.Column("drafts_created_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "communication_batches",
        sa.Column("drafts_created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("communication_batches", "drafts_created_at")
    op.drop_column("communication_batches", "drafts_created_by")
    op.drop_column("communication_batches", "drafts_created_count")
    op.drop_column("communication_batches", "drafts_provider")

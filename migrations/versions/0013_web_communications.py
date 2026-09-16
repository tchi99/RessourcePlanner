"""Add Web communication contacts, outbox batches, messages and planning snapshots.

Revision ID: 0013_web_communications
Revises: 0012_acumatica_identity_resources
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0013_web_communications"
down_revision: str | None = "0012_acumatica_identity_resources"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "communication_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recipient_id", sa.String(length=180), nullable=False),
        sa.Column("audience", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_communication_contacts_recipient",
        "communication_contacts",
        ["recipient_id"],
        unique=True,
    )
    op.create_index(
        "ix_communication_contacts_audience_active",
        "communication_contacts",
        ["audience", "active"],
        unique=False,
    )

    op.create_table(
        "communication_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("snapshot_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prepared_by", sa.String(length=255), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("communicated_by", sa.String(length=255), nullable=True),
        sa.Column("communicated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(length=255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_communication_batches_week_status",
        "communication_batches",
        ["week_start", "status"],
        unique=False,
    )
    op.create_index(
        "ix_communication_batches_fingerprint",
        "communication_batches",
        ["week_start", "kind", "snapshot_fingerprint"],
        unique=False,
    )

    op.create_table(
        "communication_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("audience", sa.String(length=32), nullable=False),
        sa.Column("recipient_id", sa.String(length=180), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("included", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["communication_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_communication_messages_batch",
        "communication_messages",
        ["batch_id", "audience"],
        unique=False,
    )

    op.create_table(
        "communication_snapshot_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.String(length=180), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=False),
        sa.Column("project_manager_id", sa.String(length=180), server_default="", nullable=False),
        sa.Column("project_number", sa.String(length=64), server_default="", nullable=False),
        sa.Column("project_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(12, 2), nullable=False),
        sa.Column("allocation_type", sa.String(length=32), server_default="Flexible", nullable=False),
        sa.Column("outside_schedule", sa.Boolean(), nullable=False),
        sa.Column("confirmation", sa.String(length=32), server_default="Confirmée", nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["communication_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_communication_snapshot_batch",
        "communication_snapshot_lines",
        ["batch_id", "day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_communication_snapshot_batch", table_name="communication_snapshot_lines")
    op.drop_table("communication_snapshot_lines")
    op.drop_index("ix_communication_messages_batch", table_name="communication_messages")
    op.drop_table("communication_messages")
    op.drop_index("ix_communication_batches_fingerprint", table_name="communication_batches")
    op.drop_index("ix_communication_batches_week_status", table_name="communication_batches")
    op.drop_table("communication_batches")
    op.drop_index("ix_communication_contacts_audience_active", table_name="communication_contacts")
    op.drop_index("ux_communication_contacts_recipient", table_name="communication_contacts")
    op.drop_table("communication_contacts")

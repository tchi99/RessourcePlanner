"""Persist project-centric communication messages and immutable projection snapshots.

Revision ID: 0029_project_communications
Revises: 0028_user_business_contacts
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0029_project_communications"
down_revision: str | None = "0028_user_business_contacts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "communication_batches",
        sa.Column(
            "model_version",
            sa.String(length=32),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "communication_batches",
        sa.Column("project_snapshot_json", sa.Text(), nullable=True),
    )

    op.add_column(
        "communication_messages",
        sa.Column("message_key", sa.String(length=180), nullable=True),
    )
    op.add_column(
        "communication_messages",
        sa.Column("project_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "communication_messages",
        sa.Column("cc_recipients_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "communication_messages",
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "communication_messages",
        sa.Column(
            "approvable",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )
    op.add_column(
        "communication_messages",
        sa.Column("diagnostics_json", sa.Text(), nullable=True),
    )
    with op.batch_alter_table("communication_messages") as batch:
        batch.alter_column(
            "recipient_email",
            existing_type=sa.String(length=320),
            nullable=True,
        )
    op.create_index(
        "ix_communication_messages_batch_key",
        "communication_messages",
        ["batch_id", "message_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_communication_messages_batch_key",
        table_name="communication_messages",
    )
    with op.batch_alter_table("communication_messages") as batch:
        batch.alter_column(
            "recipient_email",
            existing_type=sa.String(length=320),
            nullable=False,
        )
    op.drop_column("communication_messages", "diagnostics_json")
    op.drop_column("communication_messages", "approvable")
    op.drop_column("communication_messages", "content_fingerprint")
    op.drop_column("communication_messages", "cc_recipients_json")
    op.drop_column("communication_messages", "project_id")
    op.drop_column("communication_messages", "message_key")
    op.drop_column("communication_batches", "project_snapshot_json")
    op.drop_column("communication_batches", "model_version")

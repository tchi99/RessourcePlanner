"""Add versioned operational choices for approved request revisions.

Revision ID: 0032_request_operational_choices
Revises: 0031_request_approval_revisions
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0032_request_operational_choices"
down_revision: str | None = "0031_request_approval_revisions"
branch_labels: str | None = None
depends_on: str | None = None

ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "request_operational_states",
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("approval_revision_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "selections_text",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "confirmations_text",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("updated_by_name", sa.String(length=255), nullable=True),
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
        sa.CheckConstraint(
            "version >= 1",
            name="ck_request_operational_states_request_operational_state_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_request_operational_states_request",
        ),
        sa.ForeignKeyConstraint(
            ["approval_revision_id"],
            ["request_approval_revisions.id"],
            name="fk_request_operational_states_revision",
        ),
        sa.PrimaryKeyConstraint(
            "workforce_request_id",
            name="pk_request_operational_states",
        ),
    )
    op.create_index(
        "ix_request_operational_states_approval_revision_id",
        "request_operational_states",
        ["approval_revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_request_operational_states_approval_revision_id",
        table_name="request_operational_states",
    )
    op.drop_table("request_operational_states")

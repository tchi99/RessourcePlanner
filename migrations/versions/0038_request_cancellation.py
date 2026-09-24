"""Add persistent cancellation request sub-state to workforce requests.

Revision ID: 0038_request_cancellation
Revises: 0037_asset_qualification
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0038_request_cancellation"
down_revision: Union[str, Sequence[str], None] = "0037_asset_qualification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.add_column(sa.Column("cancellation_request_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("cancellation_state", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("cancellation_requested_by_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cancellation_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cancellation_resolved_by_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("cancellation_resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("cancellation_resolution_comment", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "workforce_request_cancellation_state",
            "cancellation_state IS NULL OR cancellation_state IN ('PENDING','REJECTED','ACCEPTED')",
        )
        batch_op.create_foreign_key(
            "fk_workforce_requests_cancellation_requested_by_user_id_app_users",
            "app_users",
            ["cancellation_requested_by_user_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_workforce_requests_cancellation_resolved_by_user_id_app_users",
            "app_users",
            ["cancellation_resolved_by_user_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_workforce_requests_cancellation_state",
            ["cancellation_state"],
            unique=False,
        )
        batch_op.create_index(
            "ix_workforce_requests_cancellation_requested_by_user_id",
            ["cancellation_requested_by_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_workforce_requests_cancellation_resolved_by_user_id",
            ["cancellation_resolved_by_user_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.drop_index("ix_workforce_requests_cancellation_resolved_by_user_id")
        batch_op.drop_index("ix_workforce_requests_cancellation_requested_by_user_id")
        batch_op.drop_index("ix_workforce_requests_cancellation_state")
        batch_op.drop_constraint(
            "fk_workforce_requests_cancellation_resolved_by_user_id_app_users",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_workforce_requests_cancellation_requested_by_user_id_app_users",
            type_="foreignkey",
        )
        batch_op.drop_constraint("workforce_request_cancellation_state", type_="check")
        batch_op.drop_column("cancellation_resolution_comment")
        batch_op.drop_column("cancellation_resolved_at")
        batch_op.drop_column("cancellation_resolved_by_user_id")
        batch_op.drop_column("cancellation_reason")
        batch_op.drop_column("cancellation_requested_at")
        batch_op.drop_column("cancellation_requested_by_user_id")
        batch_op.drop_column("cancellation_state")
        batch_op.drop_column("cancellation_request_id")

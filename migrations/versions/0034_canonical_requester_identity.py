"""Add stable application-user identities for demand requester and audit actor.

Revision ID: 0034_canonical_requester_identity
Revises: 0033_request_operational_budgets
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0034_canonical_requester_identity"
down_revision: str | None = "0033_request_operational_budgets"
branch_labels: str | None = None
depends_on: str | None = None

ID_LENGTH = 36


def upgrade() -> None:
    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.add_column(
            sa.Column("requester_user_id", sa.String(length=ID_LENGTH), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_workforce_requests_requester_user_id_app_users",
            "app_users",
            ["requester_user_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_workforce_requests_requester_user_id",
            ["requester_user_id"],
            unique=False,
        )

    with op.batch_alter_table("workforce_request_history") as batch_op:
        batch_op.add_column(
            sa.Column("actor_user_id", sa.String(length=ID_LENGTH), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_workforce_request_history_actor_user_id_app_users",
            "app_users",
            ["actor_user_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_workforce_request_history_actor_user_id",
            ["actor_user_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("workforce_request_history") as batch_op:
        batch_op.drop_index("ix_workforce_request_history_actor_user_id")
        batch_op.drop_constraint(
            "fk_workforce_request_history_actor_user_id_app_users",
            type_="foreignkey",
        )
        batch_op.drop_column("actor_user_id")

    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.drop_index("ix_workforce_requests_requester_user_id")
        batch_op.drop_constraint(
            "fk_workforce_requests_requester_user_id_app_users",
            type_="foreignkey",
        )
        batch_op.drop_column("requester_user_id")

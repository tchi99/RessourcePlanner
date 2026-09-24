"""Add approval scopes, approvers and stable ERP-task mappings.

Revision ID: 0039_approval_scopes
Revises: 0038_request_cancellation
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0039_approval_scopes"
down_revision: Union[str, Sequence[str], None] = "0038_request_cancellation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "approval_scopes",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
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
            name="ck_approval_scopes_approval_scope_version_positive",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_scopes"),
        sa.UniqueConstraint("code", name="uq_approval_scopes_code"),
    )
    op.create_index(
        "ix_approval_scopes_code",
        "approval_scopes",
        ["code"],
        unique=False,
    )
    op.create_index(
        "ix_approval_scopes_active",
        "approval_scopes",
        ["active"],
        unique=False,
    )

    op.create_table(
        "approval_scope_approvers",
        sa.Column(
            "approval_scope_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "app_user_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["approval_scope_id"],
            ["approval_scopes.id"],
            name="fk_scope_approver_scope",
        ),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_users.id"],
            name="fk_scope_approver_user",
        ),
        sa.PrimaryKeyConstraint(
            "approval_scope_id",
            "app_user_id",
            name="pk_approval_scope_approvers",
        ),
    )
    op.create_index(
        "ix_approval_scope_approvers_user",
        "approval_scope_approvers",
        ["app_user_id"],
        unique=False,
    )

    op.create_table(
        "task_approval_scope_mappings",
        sa.Column(
            "task_catalog_item_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "approval_scope_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_catalog_item_id"],
            ["task_catalog_items.id"],
            name="fk_task_scope_mapping_task",
        ),
        sa.ForeignKeyConstraint(
            ["approval_scope_id"],
            ["approval_scopes.id"],
            name="fk_task_scope_mapping_scope",
        ),
        sa.PrimaryKeyConstraint(
            "task_catalog_item_id",
            "approval_scope_id",
            name="pk_task_approval_scope_mappings",
        ),
    )
    op.create_index(
        "ix_task_scope_mapping_scope",
        "task_approval_scope_mappings",
        ["approval_scope_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_scope_mapping_scope",
        table_name="task_approval_scope_mappings",
    )
    op.drop_table("task_approval_scope_mappings")
    op.drop_index(
        "ix_approval_scope_approvers_user",
        table_name="approval_scope_approvers",
    )
    op.drop_table("approval_scope_approvers")
    op.drop_index(
        "ix_approval_scopes_active",
        table_name="approval_scopes",
    )
    op.drop_index(
        "ix_approval_scopes_code",
        table_name="approval_scopes",
    )
    op.drop_table("approval_scopes")

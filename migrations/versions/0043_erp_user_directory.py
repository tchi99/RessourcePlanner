"""Add the RP_Users ERP directory without changing AppUser identity.

Revision ID: 0043_erp_user_directory
Revises: 0042_employee_erp_state
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0043_erp_user_directory"
down_revision: str | None = "0042_employee_erp_state"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "erp_user_directory",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("employee_external_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("erp_user_active", sa.Boolean(), nullable=False),
        sa.Column("employee_status", sa.String(length=32), nullable=True),
        sa.Column(
            "local_active",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "roles_json",
            sa.Text(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_erp_user_directory_employee_external_id",
        "erp_user_directory",
        ["employee_external_id"],
        unique=False,
    )
    op.create_index(
        "ix_erp_user_directory_erp_user_active",
        "erp_user_directory",
        ["erp_user_active"],
        unique=False,
    )
    op.create_index(
        "ix_erp_user_directory_local_active",
        "erp_user_directory",
        ["local_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_erp_user_directory_local_active", table_name="erp_user_directory")
    op.drop_index("ix_erp_user_directory_erp_user_active", table_name="erp_user_directory")
    op.drop_index(
        "ix_erp_user_directory_employee_external_id",
        table_name="erp_user_directory",
    )
    op.drop_table("erp_user_directory")

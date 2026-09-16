"""Add Acumatica employee identity linkage and stable resource external IDs.

Revision ID: 0012_acumatica_identity_resources
Revises: 0011_oidc_sessions
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0012_acumatica_identity_resources"
down_revision: str | None = "0011_oidc_sessions"
branch_labels: str | None = None
depends_on: str | None = None


RESOURCE_EXTERNAL_INDEX = "ux_resources_external_id_not_null"
USER_EMPLOYEE_EXTERNAL_INDEX = "ux_app_users_employee_external_id_not_null"


def upgrade() -> None:
    op.add_column(
        "app_users",
        sa.Column("employee_external_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        USER_EMPLOYEE_EXTERNAL_INDEX,
        "app_users",
        ["employee_external_id"],
        unique=True,
        sqlite_where=sa.text("employee_external_id IS NOT NULL"),
        mssql_where=sa.text("employee_external_id IS NOT NULL"),
    )
    op.create_index(
        RESOURCE_EXTERNAL_INDEX,
        "resources",
        ["external_id"],
        unique=True,
        sqlite_where=sa.text("external_id IS NOT NULL"),
        mssql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(RESOURCE_EXTERNAL_INDEX, table_name="resources")
    op.drop_index(USER_EMPLOYEE_EXTERNAL_INDEX, table_name="app_users")
    op.drop_column("app_users", "employee_external_id")

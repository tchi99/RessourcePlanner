"""Add RP_ProjectTasks identity, workforce budgets and per-project sync state.

Revision ID: 0044_project_task_odata
Revises: 0043_erp_user_directory
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0044_project_task_odata"
down_revision: Union[str, Sequence[str], None] = "0043_erp_user_directory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_catalog_items",
        sa.Column("erp_task_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("account_group", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("cost_code", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("inventory_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("budget_amount_cad", sa.Numeric(precision=38, scale=10), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("budget_actual_cad", sa.Numeric(precision=38, scale=10), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("budget_diagnostic", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("workforce_eligible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("resource_class_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("average_hourly_cost_cad", sa.Numeric(precision=18, scale=4), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("budget_hours", sa.Numeric(precision=38, scale=18), nullable=True),
    )
    op.add_column(
        "task_catalog_items",
        sa.Column("workforce_diagnostics", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_task_catalog_items_erp_task_id",
        "task_catalog_items",
        ["erp_task_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_account_group",
        "task_catalog_items",
        ["account_group"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_workforce_eligible",
        "task_catalog_items",
        ["workforce_eligible"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_resource_class_code",
        "task_catalog_items",
        ["resource_class_code"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_project_workforce",
        "task_catalog_items",
        ["project_number", "active", "workforce_eligible"],
        unique=False,
    )
    op.create_index(
        "ux_task_catalog_items_erp_task_id_not_null",
        "task_catalog_items",
        ["erp_task_id"],
        unique=True,
        sqlite_where=sa.text("erp_task_id IS NOT NULL"),
        mssql_where=sa.text("erp_task_id IS NOT NULL"),
    )

    op.create_table(
        "task_catalog_project_sync_state",
        sa.Column("project_number", sa.String(length=64), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("task_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
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
        sa.PrimaryKeyConstraint(
            "project_number",
            name="pk_task_catalog_project_sync_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("task_catalog_project_sync_state")

    op.drop_index(
        "ux_task_catalog_items_erp_task_id_not_null",
        table_name="task_catalog_items",
    )
    op.drop_index(
        "ix_task_catalog_items_project_workforce",
        table_name="task_catalog_items",
    )
    op.drop_index(
        "ix_task_catalog_items_resource_class_code",
        table_name="task_catalog_items",
    )
    op.drop_index(
        "ix_task_catalog_items_workforce_eligible",
        table_name="task_catalog_items",
    )
    op.drop_index(
        "ix_task_catalog_items_account_group",
        table_name="task_catalog_items",
    )
    op.drop_index(
        "ix_task_catalog_items_erp_task_id",
        table_name="task_catalog_items",
    )
    op.drop_column("task_catalog_items", "workforce_diagnostics")
    op.drop_column("task_catalog_items", "budget_hours")
    op.drop_column("task_catalog_items", "average_hourly_cost_cad")
    op.drop_column("task_catalog_items", "resource_class_code")
    op.drop_column("task_catalog_items", "workforce_eligible")
    op.drop_column("task_catalog_items", "budget_diagnostic")
    op.drop_column("task_catalog_items", "budget_actual_cad")
    op.drop_column("task_catalog_items", "budget_amount_cad")
    op.drop_column("task_catalog_items", "inventory_id")
    op.drop_column("task_catalog_items", "cost_code")
    op.drop_column("task_catalog_items", "account_group")
    op.drop_column("task_catalog_items", "erp_task_id")

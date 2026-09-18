"""Add the durable ERP task catalog and demand task snapshots.

Revision ID: 0019_task_catalog
Revises: 0018_load_profiles
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0019_task_catalog"
down_revision: str | None = "0018_load_profiles"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "task_catalog_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_number", sa.String(length=64), nullable=False),
        sa.Column("task_code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="Actif", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("billing_rule", sa.String(length=128), nullable=True),
        sa.Column("allocation_rule", sa.String(length=128), nullable=True),
        sa.Column("completion_percent", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("erp_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("branch", sa.String(length=64), nullable=True),
        sa.Column("approver_name", sa.String(length=255), nullable=True),
        sa.Column("cv_enabled", sa.Boolean(), nullable=True),
        sa.Column("time_entry_enabled", sa.Boolean(), nullable=True),
        sa.Column("expenses_enabled", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_task_catalog_items"),
        sa.UniqueConstraint(
            "project_number",
            "task_code",
            name="uq_task_catalog_items_project_code",
        ),
    )
    op.create_index(
        "ix_task_catalog_items_project_number",
        "task_catalog_items",
        ["project_number"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_task_code",
        "task_catalog_items",
        ["task_code"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_status",
        "task_catalog_items",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_active",
        "task_catalog_items",
        ["active"],
        unique=False,
    )
    op.create_index(
        "ix_task_catalog_items_project_active",
        "task_catalog_items",
        ["project_number", "active"],
        unique=False,
    )

    op.add_column(
        "workforce_requests",
        sa.Column("erp_task_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workforce_requests",
        sa.Column("erp_task_label", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_workforce_requests_erp_task_code",
        "workforce_requests",
        ["erp_task_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workforce_requests_erp_task_code", table_name="workforce_requests")
    op.drop_column("workforce_requests", "erp_task_label")
    op.drop_column("workforce_requests", "erp_task_code")

    op.drop_index("ix_task_catalog_items_project_active", table_name="task_catalog_items")
    op.drop_index("ix_task_catalog_items_active", table_name="task_catalog_items")
    op.drop_index("ix_task_catalog_items_status", table_name="task_catalog_items")
    op.drop_index("ix_task_catalog_items_task_code", table_name="task_catalog_items")
    op.drop_index("ix_task_catalog_items_project_number", table_name="task_catalog_items")
    op.drop_table("task_catalog_items")

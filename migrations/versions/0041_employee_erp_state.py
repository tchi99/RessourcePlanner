"""Separate Acumatica employee status from local resource activation.

Revision ID: 0041_employee_erp_state
Revises: 0040_approval_cycles
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0041_employee_erp_state"
down_revision: str | None = "0040_approval_cycles"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("erp_status", sa.String(length=32), nullable=True))
    op.add_column(
        "resources",
        sa.Column("erp_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "resources",
        sa.Column("erp_department_description", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "resources",
        sa.Column("erp_department_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "resources",
        sa.Column("erp_employee_class", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "resources",
        sa.Column("erp_supervisor_external_id", sa.String(length=128), nullable=True),
    )
    op.add_column("resources", sa.Column("erp_phone", sa.String(length=64), nullable=True))
    op.add_column(
        "resources",
        sa.Column("erp_branch_code", sa.String(length=64), nullable=True),
    )
    op.add_column("resources", sa.Column("erp_contact_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_resources_erp_active",
        "resources",
        ["erp_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_resources_erp_active", table_name="resources")
    op.drop_column("resources", "erp_contact_id")
    op.drop_column("resources", "erp_branch_code")
    op.drop_column("resources", "erp_phone")
    op.drop_column("resources", "erp_supervisor_external_id")
    op.drop_column("resources", "erp_employee_class")
    op.drop_column("resources", "erp_department_code")
    op.drop_column("resources", "erp_department_description")
    op.drop_column("resources", "erp_active")
    op.drop_column("resources", "erp_status")

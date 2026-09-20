"""Capture approved contact-resolution context on materialized requirements.

Revision ID: 0027_approved_contact_context
Revises: 0026_business_contacts
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0027_approved_contact_context"
down_revision: str | None = "0026_business_contacts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.add_column(
            sa.Column(
                "approved_task_catalog_item_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "approved_operational_responsible_override_contact_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "approved_request_version",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "approved_contact_context_status",
                sa.String(length=32),
                server_default=sa.text("'LEGACY_UNKNOWN'"),
                nullable=False,
            )
        )
        batch_op.create_foreign_key(
            "fk_resource_requirements_approved_task_task_catalog",
            "task_catalog_items",
            ["approved_task_catalog_item_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_resource_requirements_approved_override_business_contacts",
            "business_contacts",
            ["approved_operational_responsible_override_contact_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_resource_requirements_approved_contact_context_status",
            "approved_contact_context_status IN "
            "('CAPTURED', 'LEGACY_UNKNOWN', 'NOT_APPLICABLE')",
        )
        batch_op.create_index(
            "ix_resource_requirements_approved_task_catalog_item_id",
            ["approved_task_catalog_item_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_resource_requirements_approved_operational_override",
            ["approved_operational_responsible_override_contact_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_resource_requirements_approved_contact_context_status",
            ["approved_contact_context_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.drop_index(
            "ix_resource_requirements_approved_contact_context_status"
        )
        batch_op.drop_index(
            "ix_resource_requirements_approved_operational_override"
        )
        batch_op.drop_index(
            "ix_resource_requirements_approved_task_catalog_item_id"
        )
        batch_op.drop_constraint(
            "ck_resource_requirements_approved_contact_context_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_resource_requirements_approved_override_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_resource_requirements_approved_task_task_catalog",
            type_="foreignkey",
        )
        batch_op.drop_column("approved_contact_context_status")
        batch_op.drop_column("approved_request_version")
        batch_op.drop_column(
            "approved_operational_responsible_override_contact_id"
        )
        batch_op.drop_column("approved_task_catalog_item_id")

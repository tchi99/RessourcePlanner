"""Add asset qualification prerequisites and operator links.

Revision ID: 0037_asset_qualification
Revises: 0036_reservable_assets
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0037_asset_qualification"
down_revision: Union[str, Sequence[str], None] = "0036_reservable_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("asset_types") as batch_op:
        batch_op.add_column(
            sa.Column(
                "qualification_policy",
                sa.String(length=32),
                server_default=sa.text("'ANY_ASSIGNED_WORKFORCE'"),
                nullable=False,
            )
        )

    op.create_table(
        "asset_type_competencies",
        sa.Column("asset_type_id", sa.String(length=36), nullable=False),
        sa.Column("competency_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_type_id"],
            ["asset_types.id"],
            name=op.f("fk_asset_type_competencies_asset_type_id_asset_types"),
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name=op.f("fk_asset_type_competencies_competency_id_competencies"),
        ),
        sa.PrimaryKeyConstraint(
            "asset_type_id",
            "competency_id",
            name=op.f("pk_asset_type_competencies"),
        ),
    )

    with op.batch_alter_table("asset_allocations") as batch_op:
        batch_op.add_column(
            sa.Column("operator_resource_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_asset_allocations_operator_resource_id_resources",
            "resources",
            ["operator_resource_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_asset_allocations_operator_resource_id",
            ["operator_resource_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_allocations") as batch_op:
        batch_op.drop_index("ix_asset_allocations_operator_resource_id")
        batch_op.drop_constraint(
            "fk_asset_allocations_operator_resource_id_resources",
            type_="foreignkey",
        )
        batch_op.drop_column("operator_resource_id")

    op.drop_table("asset_type_competencies")

    with op.batch_alter_table("asset_types") as batch_op:
        batch_op.drop_column("qualification_policy")

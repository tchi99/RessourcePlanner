"""Add canonical competency catalog and stable planning links.

Revision ID: 0020_competency_catalog
Revises: 0019_task_catalog
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0020_competency_catalog"
down_revision: str | None = "0019_task_catalog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "competencies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_competencies"),
        sa.UniqueConstraint("name", name="uq_competencies_name"),
    )
    op.create_index("ix_competencies_name", "competencies", ["name"], unique=False)
    op.create_index("ix_competencies_active", "competencies", ["active"], unique=False)
    op.create_index(
        "ix_competencies_active_order",
        "competencies",
        ["active", "sort_order"],
        unique=False,
    )

    op.create_table(
        "resource_competencies",
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("competency_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name="fk_resource_competencies_resource_id_resources",
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name="fk_resource_competencies_competency_id_competencies",
        ),
        sa.PrimaryKeyConstraint(
            "resource_id",
            "competency_id",
            name="pk_resource_competencies",
        ),
    )

    op.create_table(
        "workforce_request_competencies",
        sa.Column("workforce_request_id", sa.String(length=36), nullable=False),
        sa.Column("competency_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_workforce_request_competencies_request_id",
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name="fk_workforce_request_competencies_competency_id",
        ),
        sa.PrimaryKeyConstraint(
            "workforce_request_id",
            "competency_id",
            name="pk_workforce_request_competencies",
        ),
    )

    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.add_column(
            sa.Column("required_competency_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_index(
            "ix_resource_requirements_required_competency_id",
            ["required_competency_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_resource_requirements_required_competency_id_competencies",
            "competencies",
            ["required_competency_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.drop_constraint(
            "fk_resource_requirements_required_competency_id_competencies",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_resource_requirements_required_competency_id")
        batch_op.drop_column("required_competency_id")
    op.drop_table("workforce_request_competencies")
    op.drop_table("resource_competencies")
    op.drop_index("ix_competencies_active_order", table_name="competencies")
    op.drop_index("ix_competencies_active", table_name="competencies")
    op.drop_index("ix_competencies_name", table_name="competencies")
    op.drop_table("competencies")

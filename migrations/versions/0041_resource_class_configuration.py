"""Add workforce resource classes, task standards and project overrides.

Revision ID: 0041_resource_class_configuration
Revises: 0040_approval_cycles
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0041_resource_class_configuration"
down_revision: Union[str, Sequence[str], None] = "0040_approval_cycles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "resource_class_configs",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column(
            "average_hourly_cost_cad",
            sa.Numeric(precision=18, scale=4),
            nullable=True,
        ),
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
            name="ck_resource_class_configs_resource_class_config_version_positive",
        ),
        sa.PrimaryKeyConstraint(
            "code",
            name="pk_resource_class_configs",
        ),
    )
    op.create_index(
        "ix_resource_class_configs_active",
        "resource_class_configs",
        ["active"],
        unique=False,
    )

    op.create_table(
        "task_class_standards",
        sa.Column("task_code", sa.String(length=64), nullable=False),
        sa.Column(
            "resource_class_code",
            sa.String(length=64),
            nullable=False,
        ),
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
            name="ck_task_class_standards_task_class_standard_version_positive",
        ),
        sa.PrimaryKeyConstraint(
            "task_code",
            name="pk_task_class_standards",
        ),
    )
    op.create_index(
        "ix_task_class_standards_resource_class_code",
        "task_class_standards",
        ["resource_class_code"],
        unique=False,
    )
    op.create_index(
        "ix_task_class_standards_active",
        "task_class_standards",
        ["active"],
        unique=False,
    )

    op.create_table(
        "project_task_class_overrides",
        sa.Column(
            "project_id",
            sa.String(length=ID_LENGTH),
            nullable=False,
        ),
        sa.Column(
            "task_code",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "resource_class_code",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "excluded",
            sa.Boolean(),
            server_default=sa.false(),
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
            name="ck_project_task_class_overrides_project_task_class_override_version_positive",
        ),
        sa.CheckConstraint(
            "excluded = 1 OR resource_class_code IS NOT NULL",
            name="ck_project_task_class_overrides_project_task_class_override_value_required",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_task_class_override_project",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "task_code",
            name="pk_project_task_class_overrides",
        ),
    )
    op.create_index(
        "ix_project_task_class_overrides_resource_class_code",
        "project_task_class_overrides",
        ["resource_class_code"],
        unique=False,
    )
    op.create_index(
        "ix_project_task_class_overrides_excluded",
        "project_task_class_overrides",
        ["excluded"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_task_class_overrides_excluded",
        table_name="project_task_class_overrides",
    )
    op.drop_index(
        "ix_project_task_class_overrides_resource_class_code",
        table_name="project_task_class_overrides",
    )
    op.drop_table("project_task_class_overrides")

    op.drop_index(
        "ix_task_class_standards_active",
        table_name="task_class_standards",
    )
    op.drop_index(
        "ix_task_class_standards_resource_class_code",
        table_name="task_class_standards",
    )
    op.drop_table("task_class_standards")

    op.drop_index(
        "ix_resource_class_configs_active",
        table_name="resource_class_configs",
    )
    op.drop_table("resource_class_configs")

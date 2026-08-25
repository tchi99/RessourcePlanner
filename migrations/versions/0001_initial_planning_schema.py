"""Initial planning schema.

Revision ID: 0001_initial_planning_schema
Revises: None
Create Date: 2026-08-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_planning_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ID_LENGTH = 36


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("erp_external_id", sa.String(length=128), nullable=True),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("client", sa.String(length=255), nullable=True),
        sa.Column("project_manager_external_id", sa.String(length=128), nullable=True),
        sa.Column("project_manager_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("number", name="uq_projects_number"),
    )
    op.create_index("ix_projects_erp_external_id", "projects", ["erp_external_id"])
    op.create_index(
        "ix_projects_project_manager_external_id",
        "projects",
        ["project_manager_external_id"],
    )
    op.create_index("ix_projects_status", "projects", ["status"])

    op.create_table(
        "resources",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("resource_class", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_resources"),
    )
    op.create_index("ix_resources_active", "resources", ["active"])
    op.create_index("ix_resources_external_id", "resources", ["external_id"])
    op.create_index("ix_resources_name", "resources", ["name"])
    op.create_index("ix_resources_resource_class", "resources", ["resource_class"])

    op.create_table(
        "resource_availability_rules",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("legacy_id", sa.String(length=128), nullable=True),
        sa.Column("resource_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("availability_type", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("weekdays", sa.String(length=64), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_resource_availability_rules_availability_date_window",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name="fk_resource_availability_rules_resource_id_resources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_availability_rules"),
    )
    op.create_index(
        "ix_availability_resource_window",
        "resource_availability_rules",
        ["resource_id", "start_date", "end_date"],
    )
    op.create_index(
        "ix_resource_availability_rules_active",
        "resource_availability_rules",
        ["active"],
    )
    op.create_index(
        "ix_resource_availability_rules_availability_type",
        "resource_availability_rules",
        ["availability_type"],
    )
    op.create_index(
        "ix_resource_availability_rules_legacy_id",
        "resource_availability_rules",
        ["legacy_id"],
    )
    op.create_index(
        "ix_resource_availability_rules_resource_id",
        "resource_availability_rules",
        ["resource_id"],
    )

    op.create_table(
        "work_packages",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("project_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("planned_hours", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("legacy_effort_id", sa.String(length=128), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_work_packages_work_package_date_window",
        ),
        sa.CheckConstraint(
            "planned_hours IS NULL OR planned_hours >= 0",
            name="ck_work_packages_work_package_hours_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_work_packages_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_work_packages"),
    )
    op.create_index("ix_work_packages_code", "work_packages", ["code"])
    op.create_index("ix_work_packages_legacy_effort_id", "work_packages", ["legacy_effort_id"])
    op.create_index("ix_work_packages_project_id", "work_packages", ["project_id"])
    op.create_index(
        "ix_work_packages_project_status",
        "work_packages",
        ["project_id", "status"],
    )
    op.create_index("ix_work_packages_status", "work_packages", ["status"])

    op.create_table(
        "workforce_requests",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("legacy_demand_number", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("work_package_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("requester_external_id", sa.String(length=128), nullable=True),
        sa.Column("requester_name", sa.String(length=255), nullable=True),
        sa.Column("request_type", sa.String(length=64), nullable=False, server_default=sa.text("'Projet'")),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default=sa.text("'Normale'")),
        sa.Column("confirmation", sa.String(length=32), nullable=False, server_default=sa.text("'Confirmée'")),
        sa.Column("desired_start", sa.Date(), nullable=True),
        sa.Column("desired_end", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("site_client", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("resource_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("required_competencies", sa.Text(), nullable=True),
        sa.Column("estimated_hours", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("estimated_days", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("proposed_resource_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'Brouillon'")),
        sa.Column("approved_by_external_id", sa.String(length=128), nullable=True),
        sa.Column("approved_by_name", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "desired_end IS NULL OR desired_start IS NULL OR desired_end >= desired_start",
            name="ck_workforce_requests_workforce_request_date_window",
        ),
        sa.CheckConstraint(
            "estimated_days IS NULL OR estimated_days >= 0",
            name="ck_workforce_requests_workforce_request_days_non_negative",
        ),
        sa.CheckConstraint(
            "estimated_hours IS NULL OR estimated_hours >= 0",
            name="ck_workforce_requests_workforce_request_hours_non_negative",
        ),
        sa.CheckConstraint(
            "resource_count >= 1",
            name="ck_workforce_requests_workforce_request_resource_count",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_workforce_requests_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_resource_id"],
            ["resources.id"],
            name="fk_workforce_requests_proposed_resource_id_resources",
        ),
        sa.ForeignKeyConstraint(
            ["work_package_id"],
            ["work_packages.id"],
            name="fk_workforce_requests_work_package_id_work_packages",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workforce_requests"),
    )
    op.create_index("ix_workforce_requests_confirmation", "workforce_requests", ["confirmation"])
    op.create_index("ix_workforce_requests_desired_end", "workforce_requests", ["desired_end"])
    op.create_index("ix_workforce_requests_desired_start", "workforce_requests", ["desired_start"])
    op.create_index(
        "ix_workforce_requests_legacy_demand_number",
        "workforce_requests",
        ["legacy_demand_number"],
    )
    op.create_index("ix_workforce_requests_priority", "workforce_requests", ["priority"])
    op.create_index("ix_workforce_requests_project_id", "workforce_requests", ["project_id"])
    op.create_index(
        "ix_workforce_requests_project_status",
        "workforce_requests",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_workforce_requests_proposed_resource_id",
        "workforce_requests",
        ["proposed_resource_id"],
    )
    op.create_index("ix_workforce_requests_status", "workforce_requests", ["status"])
    op.create_index(
        "ix_workforce_requests_window",
        "workforce_requests",
        ["desired_start", "desired_end"],
    )
    op.create_index(
        "ix_workforce_requests_work_package_id",
        "workforce_requests",
        ["work_package_id"],
    )

    op.create_table(
        "resource_requirements",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("legacy_segment_id", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("assigned_resource_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("planned_hours", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'À assigner'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_effort_id", sa.String(length=128), nullable=True),
        sa.Column("required_competency", sa.String(length=128), nullable=True),
        sa.Column("planning_type", sa.String(length=32), nullable=False, server_default=sa.text("'Flexible'")),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default=sa.text("'Normale'")),
        sa.Column("outside_standard_hours_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("origin", sa.String(length=32), nullable=False, server_default=sa.text("'REQUEST'")),
        sa.Column("created_by_external_id", sa.String(length=128), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="ck_resource_requirements_resource_requirement_date_window",
        ),
        sa.CheckConstraint(
            "planned_hours > 0",
            name="ck_resource_requirements_resource_requirement_hours_positive",
        ),
        sa.CheckConstraint(
            "workforce_request_id IS NOT NULL OR origin IN ('QUICK_SHIFT', 'AD_HOC')",
            name="ck_resource_requirements_resource_requirement_request_or_adhoc",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_resource_id"],
            ["resources.id"],
            name="fk_resource_requirements_assigned_resource_id_resources",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_resource_requirements_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_resource_requirements_workforce_request_id_workforce_requests",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_requirements"),
    )
    op.create_index(
        "ix_resource_requirements_assigned_resource_id",
        "resource_requirements",
        ["assigned_resource_id"],
    )
    op.create_index(
        "ix_resource_requirements_legacy_segment_id",
        "resource_requirements",
        ["legacy_segment_id"],
    )
    op.create_index("ix_resource_requirements_origin", "resource_requirements", ["origin"])
    op.create_index(
        "ix_resource_requirements_planning_type",
        "resource_requirements",
        ["planning_type"],
    )
    op.create_index("ix_resource_requirements_priority", "resource_requirements", ["priority"])
    op.create_index("ix_resource_requirements_project_id", "resource_requirements", ["project_id"])
    op.create_index(
        "ix_resource_requirements_project_window",
        "resource_requirements",
        ["project_id", "start_date", "end_date"],
    )
    op.create_index(
        "ix_resource_requirements_request_status",
        "resource_requirements",
        ["workforce_request_id", "status"],
    )
    op.create_index(
        "ix_resource_requirements_required_competency",
        "resource_requirements",
        ["required_competency"],
    )
    op.create_index(
        "ix_resource_requirements_resource_window",
        "resource_requirements",
        ["assigned_resource_id", "start_date", "end_date"],
    )
    op.create_index(
        "ix_resource_requirements_source_effort_id",
        "resource_requirements",
        ["source_effort_id"],
    )
    op.create_index("ix_resource_requirements_status", "resource_requirements", ["status"])
    op.create_index(
        "ix_resource_requirements_workforce_request_id",
        "resource_requirements",
        ["workforce_request_id"],
    )

    op.create_table(
        "workforce_request_history",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor_external_id", sa.String(length=128), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_workforce_request_history_workforce_request_id_workforce_requests",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workforce_request_history"),
    )
    op.create_index(
        "ix_workforce_request_history_request_time",
        "workforce_request_history",
        ["workforce_request_id", "occurred_at"],
    )
    op.create_index(
        "ix_workforce_request_history_workforce_request_id",
        "workforce_request_history",
        ["workforce_request_id"],
    )

    op.create_table(
        "shifts",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("legacy_allocation_id", sa.String(length=64), nullable=True),
        sa.Column("resource_requirement_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("resource_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("allocation_type", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'AUTO'")),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outside_standard_hours", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmation", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("hours > 0", name="ck_shifts_shift_hours_positive"),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name="fk_shifts_resource_id_resources",
        ),
        sa.ForeignKeyConstraint(
            ["resource_requirement_id"],
            ["resource_requirements.id"],
            name="fk_shifts_resource_requirement_id_resource_requirements",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shifts"),
    )
    op.create_index("ix_shifts_allocation_type", "shifts", ["allocation_type"])
    op.create_index("ix_shifts_legacy_allocation_id", "shifts", ["legacy_allocation_id"])
    op.create_index("ix_shifts_locked", "shifts", ["locked"])
    op.create_index("ix_shifts_locked_date", "shifts", ["locked", "work_date"])
    op.create_index(
        "ix_shifts_requirement_date",
        "shifts",
        ["resource_requirement_id", "work_date"],
    )
    op.create_index("ix_shifts_resource_date", "shifts", ["resource_id", "work_date"])
    op.create_index("ix_shifts_resource_id", "shifts", ["resource_id"])
    op.create_index(
        "ix_shifts_resource_requirement_id",
        "shifts",
        ["resource_requirement_id"],
    )
    op.create_index("ix_shifts_source", "shifts", ["source"])
    op.create_index("ix_shifts_work_date", "shifts", ["work_date"])


def downgrade() -> None:
    op.drop_index("ix_shifts_work_date", table_name="shifts")
    op.drop_index("ix_shifts_source", table_name="shifts")
    op.drop_index("ix_shifts_resource_requirement_id", table_name="shifts")
    op.drop_index("ix_shifts_resource_id", table_name="shifts")
    op.drop_index("ix_shifts_resource_date", table_name="shifts")
    op.drop_index("ix_shifts_requirement_date", table_name="shifts")
    op.drop_index("ix_shifts_locked_date", table_name="shifts")
    op.drop_index("ix_shifts_locked", table_name="shifts")
    op.drop_index("ix_shifts_legacy_allocation_id", table_name="shifts")
    op.drop_index("ix_shifts_allocation_type", table_name="shifts")
    op.drop_table("shifts")

    op.drop_index(
        "ix_workforce_request_history_workforce_request_id",
        table_name="workforce_request_history",
    )
    op.drop_index(
        "ix_workforce_request_history_request_time",
        table_name="workforce_request_history",
    )
    op.drop_table("workforce_request_history")

    op.drop_index(
        "ix_resource_requirements_workforce_request_id",
        table_name="resource_requirements",
    )
    op.drop_index("ix_resource_requirements_status", table_name="resource_requirements")
    op.drop_index(
        "ix_resource_requirements_source_effort_id",
        table_name="resource_requirements",
    )
    op.drop_index(
        "ix_resource_requirements_resource_window",
        table_name="resource_requirements",
    )
    op.drop_index(
        "ix_resource_requirements_required_competency",
        table_name="resource_requirements",
    )
    op.drop_index(
        "ix_resource_requirements_request_status",
        table_name="resource_requirements",
    )
    op.drop_index(
        "ix_resource_requirements_project_window",
        table_name="resource_requirements",
    )
    op.drop_index("ix_resource_requirements_project_id", table_name="resource_requirements")
    op.drop_index("ix_resource_requirements_priority", table_name="resource_requirements")
    op.drop_index("ix_resource_requirements_planning_type", table_name="resource_requirements")
    op.drop_index("ix_resource_requirements_origin", table_name="resource_requirements")
    op.drop_index("ix_resource_requirements_legacy_segment_id", table_name="resource_requirements")
    op.drop_index("ix_resource_requirements_assigned_resource_id", table_name="resource_requirements")
    op.drop_table("resource_requirements")

    op.drop_index("ix_workforce_requests_work_package_id", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_window", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_status", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_proposed_resource_id", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_project_status", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_project_id", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_priority", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_legacy_demand_number", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_desired_start", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_desired_end", table_name="workforce_requests")
    op.drop_index("ix_workforce_requests_confirmation", table_name="workforce_requests")
    op.drop_table("workforce_requests")

    op.drop_index("ix_work_packages_status", table_name="work_packages")
    op.drop_index("ix_work_packages_project_status", table_name="work_packages")
    op.drop_index("ix_work_packages_project_id", table_name="work_packages")
    op.drop_index("ix_work_packages_legacy_effort_id", table_name="work_packages")
    op.drop_index("ix_work_packages_code", table_name="work_packages")
    op.drop_table("work_packages")

    op.drop_index(
        "ix_resource_availability_rules_resource_id",
        table_name="resource_availability_rules",
    )
    op.drop_index(
        "ix_resource_availability_rules_legacy_id",
        table_name="resource_availability_rules",
    )
    op.drop_index(
        "ix_resource_availability_rules_availability_type",
        table_name="resource_availability_rules",
    )
    op.drop_index(
        "ix_resource_availability_rules_active",
        table_name="resource_availability_rules",
    )
    op.drop_index(
        "ix_availability_resource_window",
        table_name="resource_availability_rules",
    )
    op.drop_table("resource_availability_rules")

    op.drop_index("ix_resources_resource_class", table_name="resources")
    op.drop_index("ix_resources_name", table_name="resources")
    op.drop_index("ix_resources_external_id", table_name="resources")
    op.drop_index("ix_resources_active", table_name="resources")
    op.drop_table("resources")

    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_project_manager_external_id", table_name="projects")
    op.drop_index("ix_projects_erp_external_id", table_name="projects")
    op.drop_table("projects")

"""Add RequestLine persistence and backfill one legacy line per request.

Revision ID: 0022_request_lines
Revises: 0021_auth_security
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0022_request_lines"
down_revision: str | None = "0021_auth_security"
branch_labels: str | None = None
depends_on: str | None = None


ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "request_lines",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "kind",
            sa.String(length=32),
            server_default=sa.text("'WORKFORCE'"),
            nullable=False,
        ),
        sa.Column("slot_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("required_resource_class", sa.String(length=64), nullable=True),
        sa.Column("required_competencies_snapshot", sa.Text(), nullable=True),
        sa.Column("desired_start", sa.Date(), nullable=True),
        sa.Column("desired_end", sa.Date(), nullable=True),
        sa.Column("desired_active_days", sa.Numeric(12, 2), nullable=True),
        sa.Column("estimated_hours", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "confirmation",
            sa.String(length=32),
            server_default=sa.text("'Confirmée'"),
            nullable=False,
        ),
        sa.Column("work_package_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("task_catalog_item_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("erp_task_code", sa.String(length=64), nullable=True),
        sa.Column("erp_task_label", sa.String(length=255), nullable=True),
        sa.Column("proposed_resource_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
            "position >= 0",
            name="ck_request_lines_request_line_position_non_negative",
        ),
        sa.CheckConstraint(
            "slot_count >= 1",
            name="ck_request_lines_request_line_slot_count_positive",
        ),
        sa.CheckConstraint(
            "kind IN ('WORKFORCE', 'ASSET', 'WORKCENTER')",
            name="ck_request_lines_request_line_kind_supported",
        ),
        sa.CheckConstraint(
            "desired_end IS NULL OR desired_start IS NULL OR desired_end >= desired_start",
            name="ck_request_lines_request_line_date_window",
        ),
        sa.CheckConstraint(
            "estimated_hours IS NULL OR estimated_hours >= 0",
            name="ck_request_lines_request_line_hours_non_negative",
        ),
        sa.CheckConstraint(
            "desired_active_days IS NULL OR desired_active_days >= 0",
            name="ck_request_lines_request_line_days_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_request_lines_workforce_request_id_workforce_requests",
        ),
        sa.ForeignKeyConstraint(
            ["work_package_id"],
            ["work_packages.id"],
            name="fk_request_lines_work_package_id_work_packages",
        ),
        sa.ForeignKeyConstraint(
            ["task_catalog_item_id"],
            ["task_catalog_items.id"],
            name="fk_request_lines_task_catalog_item_id_task_catalog_items",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_resource_id"],
            ["resources.id"],
            name="fk_request_lines_proposed_resource_id_resources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_request_lines"),
    )
    for index_name, columns in (
        ("ix_request_lines_workforce_request_id", ["workforce_request_id"]),
        ("ix_request_lines_kind", ["kind"]),
        ("ix_request_lines_required_resource_class", ["required_resource_class"]),
        ("ix_request_lines_desired_start", ["desired_start"]),
        ("ix_request_lines_desired_end", ["desired_end"]),
        ("ix_request_lines_confirmation", ["confirmation"]),
        ("ix_request_lines_work_package_id", ["work_package_id"]),
        ("ix_request_lines_task_catalog_item_id", ["task_catalog_item_id"]),
        ("ix_request_lines_erp_task_code", ["erp_task_code"]),
        ("ix_request_lines_proposed_resource_id", ["proposed_resource_id"]),
        ("ix_request_lines_active", ["active"]),
        ("ix_request_lines_request_position", ["workforce_request_id", "position"]),
        ("ix_request_lines_request_active", ["workforce_request_id", "active"]),
        ("ix_request_lines_window", ["desired_start", "desired_end"]),
    ):
        op.create_index(index_name, "request_lines", columns, unique=False)

    op.create_table(
        "request_line_competencies",
        sa.Column("request_line_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("competency_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_line_id"],
            ["request_lines.id"],
            name="fk_request_line_competencies_request_line_id_request_lines",
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name="fk_request_line_competencies_competency_id_competencies",
        ),
        sa.PrimaryKeyConstraint(
            "request_line_id",
            "competency_id",
            name="pk_request_line_competencies",
        ),
    )

    op.create_table(
        "resource_requirement_competencies",
        sa.Column("resource_requirement_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("competency_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.ForeignKeyConstraint(
            ["resource_requirement_id"],
            ["resource_requirements.id"],
            name=(
                "fk_resource_requirement_competencies_resource_requirement_id_"
                "resource_requirements"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name="fk_resource_requirement_competencies_competency_id_competencies",
        ),
        sa.PrimaryKeyConstraint(
            "resource_requirement_id",
            "competency_id",
            name="pk_resource_requirement_competencies",
        ),
    )

    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.add_column(
            sa.Column("source_request_line_id", sa.String(length=ID_LENGTH), nullable=True)
        )
        batch_op.create_index(
            "ix_resource_requirements_source_request_line_id",
            ["source_request_line_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_resource_requirements_source_request_line_id_request_lines",
            "request_lines",
            ["source_request_line_id"],
            ["id"],
        )

    with op.batch_alter_table("workforce_request_periods") as batch_op:
        batch_op.add_column(
            sa.Column("request_line_id", sa.String(length=ID_LENGTH), nullable=True)
        )
        batch_op.create_index(
            "ix_workforce_request_periods_request_line_id",
            ["request_line_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_workforce_request_periods_request_line_id_request_lines",
            "request_lines",
            ["request_line_id"],
            ["id"],
        )

    with op.batch_alter_table("workforce_request_period_selections") as batch_op:
        batch_op.add_column(
            sa.Column("request_line_id", sa.String(length=ID_LENGTH), nullable=True)
        )
        batch_op.create_index(
            "ix_workforce_request_period_selections_request_line_id",
            ["request_line_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_workforce_request_period_selections_request_line_id_request_lines",
            "request_lines",
            ["request_line_id"],
            ["id"],
        )

    # Deterministic one-line backfill. Reusing the request UUID makes every legacy
    # relationship easy to reconnect without generating database-specific UUIDs.
    op.execute(
        sa.text(
            """
            INSERT INTO request_lines (
                id,
                workforce_request_id,
                position,
                kind,
                slot_count,
                required_resource_class,
                required_competencies_snapshot,
                desired_start,
                desired_end,
                desired_active_days,
                estimated_hours,
                confirmation,
                work_package_id,
                task_catalog_item_id,
                erp_task_code,
                erp_task_label,
                proposed_resource_id,
                description,
                created_at,
                updated_at
            )
            SELECT
                wr.id,
                wr.id,
                0,
                'WORKFORCE',
                wr.resource_count,
                NULL,
                wr.required_competencies,
                wr.desired_start,
                wr.desired_end,
                wr.estimated_days,
                wr.estimated_hours,
                wr.confirmation,
                wr.work_package_id,
                tc.id,
                wr.erp_task_code,
                wr.erp_task_label,
                wr.proposed_resource_id,
                wr.description,
                wr.created_at,
                wr.updated_at
            FROM workforce_requests wr
            JOIN projects p
              ON p.id = wr.project_id
            LEFT JOIN task_catalog_items tc
              ON tc.project_number = p.number
             AND tc.task_code = wr.erp_task_code
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO request_line_competencies (request_line_id, competency_id)
            SELECT workforce_request_id, competency_id
            FROM workforce_request_competencies
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO resource_requirement_competencies (
                resource_requirement_id,
                competency_id
            )
            SELECT rr.id, wrc.competency_id
            FROM resource_requirements rr
            JOIN workforce_request_competencies wrc
              ON wrc.workforce_request_id = rr.workforce_request_id
            WHERE rr.workforce_request_id IS NOT NULL
            UNION
            SELECT rr.id, rr.required_competency_id
            FROM resource_requirements rr
            WHERE rr.required_competency_id IS NOT NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE resource_requirements
            SET source_request_line_id = workforce_request_id
            WHERE workforce_request_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE workforce_request_periods
            SET request_line_id = workforce_request_id
            WHERE workforce_request_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE workforce_request_period_selections
            SET request_line_id = workforce_request_id
            WHERE workforce_request_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("workforce_request_period_selections") as batch_op:
        batch_op.drop_constraint(
            "fk_workforce_request_period_selections_request_line_id_request_lines",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_workforce_request_period_selections_request_line_id")
        batch_op.drop_column("request_line_id")

    with op.batch_alter_table("workforce_request_periods") as batch_op:
        batch_op.drop_constraint(
            "fk_workforce_request_periods_request_line_id_request_lines",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_workforce_request_periods_request_line_id")
        batch_op.drop_column("request_line_id")

    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.drop_constraint(
            "fk_resource_requirements_source_request_line_id_request_lines",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_resource_requirements_source_request_line_id")
        batch_op.drop_column("source_request_line_id")

    op.drop_table("resource_requirement_competencies")
    op.drop_table("request_line_competencies")

    for index_name in (
        "ix_request_lines_window",
        "ix_request_lines_request_active",
        "ix_request_lines_request_position",
        "ix_request_lines_active",
        "ix_request_lines_proposed_resource_id",
        "ix_request_lines_erp_task_code",
        "ix_request_lines_task_catalog_item_id",
        "ix_request_lines_work_package_id",
        "ix_request_lines_confirmation",
        "ix_request_lines_desired_end",
        "ix_request_lines_desired_start",
        "ix_request_lines_required_resource_class",
        "ix_request_lines_kind",
        "ix_request_lines_workforce_request_id",
    ):
        op.drop_index(index_name, table_name="request_lines")
    op.drop_table("request_lines")

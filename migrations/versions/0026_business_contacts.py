"""Add canonical business contacts and explicit ownership relationships.

Revision ID: 0026_business_contacts
Revises: 0025_requirement_resource_class
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from alembic import context, op
import sqlalchemy as sa


revision: str = "0026_business_contacts"
down_revision: str | None = "0025_requirement_resource_class"
branch_labels: str | None = None
depends_on: str | None = None


def _contact_id(external_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"resourceplanner:business-contact:project-manager:{external_id}",
        )
    )


def _backfill_project_manager_contacts() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    projects = sa.table(
        "projects",
        sa.column("id", sa.String(length=36)),
        sa.column("number", sa.String(length=64)),
        sa.column("project_manager_external_id", sa.String(length=128)),
        sa.column("project_manager_name", sa.String(length=255)),
        sa.column("project_manager_contact_id", sa.String(length=36)),
    )
    contacts = sa.table(
        "business_contacts",
        sa.column("id", sa.String(length=36)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("email", sa.String(length=320)),
        sa.column("phone", sa.String(length=64)),
        sa.column("active", sa.Boolean()),
        sa.column("source", sa.String(length=32)),
        sa.column("external_system", sa.String(length=64)),
        sa.column("external_entity", sa.String(length=64)),
        sa.column("external_id", sa.String(length=128)),
        sa.column("version", sa.Integer()),
    )

    rows = bind.execute(
        sa.select(
            projects.c.number,
            projects.c.project_manager_external_id,
            projects.c.project_manager_name,
        )
        .where(projects.c.project_manager_external_id.is_not(None))
        .order_by(projects.c.project_manager_external_id, projects.c.number)
    ).mappings().all()

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        external_id = str(row["project_manager_external_id"] or "").strip()
        if not external_id:
            continue
        grouped.setdefault(external_id, []).append(dict(row))

    for external_id, manager_rows in grouped.items():
        display_name = next(
            (
                str(row["project_manager_name"]).strip()
                for row in manager_rows
                if row.get("project_manager_name")
                and str(row["project_manager_name"]).strip()
            ),
            external_id,
        )
        contact_id = _contact_id(external_id)
        bind.execute(
            contacts.insert().values(
                id=contact_id,
                display_name=display_name,
                email=None,
                phone=None,
                active=True,
                source="MIGRATION",
                external_system="RESOURCEPLANNER",
                external_entity="EMPLOYEE",
                external_id=external_id,
                version=1,
            )
        )
        bind.execute(
            projects.update()
            .where(projects.c.project_manager_external_id == external_id)
            .values(project_manager_contact_id=contact_id)
        )


def upgrade() -> None:
    op.create_table(
        "business_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            server_default=sa.text("'LOCAL'"),
            nullable=False,
        ),
        sa.Column("external_system", sa.String(length=64), nullable=True),
        sa.Column("external_entity", sa.String(length=64), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
            "external_id IS NULL OR "
            "(external_system IS NOT NULL AND external_entity IS NOT NULL)",
            name="ck_business_contacts_business_contact_external_identity_complete",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_business_contacts_business_contact_version_positive",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_business_contacts"),
    )
    op.create_index(
        "ix_business_contacts_display_name",
        "business_contacts",
        ["display_name"],
        unique=False,
    )
    op.create_index(
        "ix_business_contacts_active",
        "business_contacts",
        ["active"],
        unique=False,
    )
    op.create_index(
        "ix_business_contacts_source",
        "business_contacts",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ux_business_contacts_ext_identity",
        "business_contacts",
        ["external_system", "external_entity", "external_id"],
        unique=True,
        sqlite_where=sa.text("external_id IS NOT NULL"),
        postgresql_where=sa.text("external_id IS NOT NULL"),
        mssql_where=sa.text("external_id IS NOT NULL"),
    )

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column("project_manager_contact_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_projects_project_manager_contact_id_business_contacts",
            "business_contacts",
            ["project_manager_contact_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_projects_project_manager_contact_id",
            ["project_manager_contact_id"],
            unique=False,
        )

    with op.batch_alter_table("task_catalog_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "operational_responsible_contact_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("coordinator_contact_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_task_catalog_items_operational_contact_business_contacts",
            "business_contacts",
            ["operational_responsible_contact_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_task_catalog_items_coordinator_contact_business_contacts",
            "business_contacts",
            ["coordinator_contact_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_task_catalog_items_operational_contact",
            ["operational_responsible_contact_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_task_catalog_items_coordinator_contact",
            ["coordinator_contact_id"],
            unique=False,
        )

    with op.batch_alter_table("resources") as batch_op:
        batch_op.add_column(
            sa.Column("coordinator_contact_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_resources_coordinator_contact_id_business_contacts",
            "business_contacts",
            ["coordinator_contact_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_resources_coordinator_contact_id",
            ["coordinator_contact_id"],
            unique=False,
        )

    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "operational_responsible_override_contact_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_workforce_requests_operational_override_business_contacts",
            "business_contacts",
            ["operational_responsible_override_contact_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_workforce_requests_operational_override_contact",
            ["operational_responsible_override_contact_id"],
            unique=False,
        )

    _backfill_project_manager_contacts()


def downgrade() -> None:
    with op.batch_alter_table("workforce_requests") as batch_op:
        batch_op.drop_index("ix_workforce_requests_operational_override_contact")
        batch_op.drop_constraint(
            "fk_workforce_requests_operational_override_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_column("operational_responsible_override_contact_id")

    with op.batch_alter_table("resources") as batch_op:
        batch_op.drop_index("ix_resources_coordinator_contact_id")
        batch_op.drop_constraint(
            "fk_resources_coordinator_contact_id_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_column("coordinator_contact_id")

    with op.batch_alter_table("task_catalog_items") as batch_op:
        batch_op.drop_index("ix_task_catalog_items_coordinator_contact")
        batch_op.drop_index("ix_task_catalog_items_operational_contact")
        batch_op.drop_constraint(
            "fk_task_catalog_items_coordinator_contact_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_task_catalog_items_operational_contact_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_column("coordinator_contact_id")
        batch_op.drop_column("operational_responsible_contact_id")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index("ix_projects_project_manager_contact_id")
        batch_op.drop_constraint(
            "fk_projects_project_manager_contact_id_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_column("project_manager_contact_id")

    op.drop_index("ux_business_contacts_ext_identity", table_name="business_contacts")
    op.drop_index("ix_business_contacts_source", table_name="business_contacts")
    op.drop_index("ix_business_contacts_active", table_name="business_contacts")
    op.drop_index("ix_business_contacts_display_name", table_name="business_contacts")
    op.drop_table("business_contacts")

"""Link each application user to one canonical business contact.

Revision ID: 0028_user_business_contacts
Revises: 0027_approved_contact_context
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from alembic import context, op
import sqlalchemy as sa


revision: str = "0028_user_business_contacts"
down_revision: str | None = "0027_approved_contact_context"
branch_labels: str | None = None
depends_on: str | None = None


def _contact_id(user_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"resourceplanner:business-contact:app-user:{user_id}",
        )
    )


def _backfill_user_contacts() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    users = sa.table(
        "app_users",
        sa.column("id", sa.String(length=36)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("email", sa.String(length=320)),
        sa.column("employee_external_id", sa.String(length=128)),
        sa.column("active", sa.Boolean()),
        sa.column("business_contact_id", sa.String(length=36)),
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
            users.c.id,
            users.c.display_name,
            users.c.email,
            users.c.employee_external_id,
            users.c.active,
        ).order_by(users.c.id)
    ).mappings().all()

    for row in rows:
        user_id = str(row["id"])
        external_id = str(row["employee_external_id"] or "").strip() or None
        contact = None
        if external_id:
            contact = bind.execute(
                sa.select(contacts.c.id, contacts.c.version).where(
                    contacts.c.external_system == "RESOURCEPLANNER",
                    contacts.c.external_entity == "EMPLOYEE",
                    contacts.c.external_id == external_id,
                )
            ).mappings().first()

        if contact is None:
            deterministic_id = _contact_id(user_id)
            contact = bind.execute(
                sa.select(contacts.c.id, contacts.c.version).where(
                    contacts.c.id == deterministic_id
                )
            ).mappings().first()

        if contact is None:
            contact_id = _contact_id(user_id)
            bind.execute(
                contacts.insert().values(
                    id=contact_id,
                    display_name=str(row["display_name"]),
                    email=row["email"],
                    phone=None,
                    active=bool(row["active"]),
                    source="APP_USER",
                    external_system=("RESOURCEPLANNER" if external_id else None),
                    external_entity=("EMPLOYEE" if external_id else None),
                    external_id=external_id,
                    version=1,
                )
            )
        else:
            contact_id = str(contact["id"])
            bind.execute(
                contacts.update()
                .where(contacts.c.id == contact_id)
                .values(
                    display_name=str(row["display_name"]),
                    email=row["email"],
                    active=bool(row["active"]),
                    source="APP_USER",
                    version=max(int(contact["version"] or 1), 1) + 1,
                )
            )

        bind.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(business_contact_id=contact_id)
        )


def upgrade() -> None:
    with op.batch_alter_table("app_users") as batch_op:
        batch_op.add_column(
            sa.Column("business_contact_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_app_users_business_contact_id_business_contacts",
            "business_contacts",
            ["business_contact_id"],
            ["id"],
        )

    _backfill_user_contacts()

    op.create_index(
        "ux_app_users_business_contact_id_not_null",
        "app_users",
        ["business_contact_id"],
        unique=True,
        sqlite_where=sa.text("business_contact_id IS NOT NULL"),
        postgresql_where=sa.text("business_contact_id IS NOT NULL"),
        mssql_where=sa.text("business_contact_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_app_users_business_contact_id_not_null",
        table_name="app_users",
    )
    with op.batch_alter_table("app_users") as batch_op:
        batch_op.drop_constraint(
            "fk_app_users_business_contact_id_business_contacts",
            type_="foreignkey",
        )
        batch_op.drop_column("business_contact_id")

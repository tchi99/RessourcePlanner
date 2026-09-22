"""Add immutable request approval revisions and authorization provenance.

Revision ID: 0031_request_approval_revisions
Revises: 0030_smtp_delivery
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0031_request_approval_revisions"
down_revision: str | None = "0030_smtp_delivery"
branch_labels: str | None = None
depends_on: str | None = None

ID_LENGTH = 36


def upgrade() -> None:
    op.create_table(
        "request_approval_revisions",
        sa.Column("id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("previous_revision_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column("request_version", sa.Integer(), nullable=False),
        sa.Column("approved_by_external_id", sa.String(length=128), nullable=True),
        sa.Column("approved_by_name", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "provenance",
            sa.String(length=64),
            server_default=sa.text("'APPROVAL'"),
            nullable=False,
        ),
        sa.Column(
            "payload_format_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("payload_text", sa.Text(), nullable=False),
        sa.Column("authorization_fingerprint", sa.String(length=64), nullable=False),
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
            "request_version >= 1",
            name="ck_request_approval_revisions_request_approval_revision_request_version_positive",
        ),
        sa.CheckConstraint(
            "payload_format_version >= 1",
            name="ck_request_approval_revisions_request_approval_revision_format_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_request_approval_revisions_workforce_request_id_workforce_requests",
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id"],
            ["request_approval_revisions.id"],
            name="fk_request_approval_revisions_previous_revision_id_request_approval_revisions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_request_approval_revisions"),
    )
    op.create_index(
        "ix_request_approval_revisions_workforce_request_id",
        "request_approval_revisions",
        ["workforce_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_request_approval_revisions_previous_revision_id",
        "request_approval_revisions",
        ["previous_revision_id"],
        unique=False,
    )
    op.create_index(
        "ix_request_approval_revision_request_created",
        "request_approval_revisions",
        ["workforce_request_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_request_approval_revision_fingerprint",
        "request_approval_revisions",
        ["authorization_fingerprint"],
        unique=False,
    )

    op.create_table(
        "request_approval_references",
        sa.Column("workforce_request_id", sa.String(length=ID_LENGTH), nullable=False),
        sa.Column("active_revision_id", sa.String(length=ID_LENGTH), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'LEGACY_UNKNOWN'"),
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
            "status IN ('CAPTURED', 'LEGACY_UNKNOWN')",
            name="ck_request_approval_references_request_approval_reference_status",
        ),
        sa.ForeignKeyConstraint(
            ["workforce_request_id"],
            ["workforce_requests.id"],
            name="fk_request_approval_references_workforce_request_id_workforce_requests",
        ),
        sa.ForeignKeyConstraint(
            ["active_revision_id"],
            ["request_approval_revisions.id"],
            name="fk_request_approval_references_active_revision_id_request_approval_revisions",
        ),
        sa.PrimaryKeyConstraint(
            "workforce_request_id",
            name="pk_request_approval_references",
        ),
    )
    op.create_index(
        "ix_request_approval_reference_active_revision",
        "request_approval_references",
        ["active_revision_id"],
        unique=False,
    )

    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.add_column(
            sa.Column("approval_revision_id", sa.String(length=ID_LENGTH), nullable=True)
        )
        batch_op.add_column(
            sa.Column("approved_entry_key", sa.String(length=512), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "approval_reference_status",
                sa.String(length=32),
                server_default=sa.text("'LEGACY_UNKNOWN'"),
                nullable=False,
            )
        )
        batch_op.create_foreign_key(
            "fk_resource_requirements_approval_revision_id_request_approval_revisions",
            "request_approval_revisions",
            ["approval_revision_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "resource_requirement_approval_reference_status",
            "approval_reference_status IN ('CAPTURED', 'LEGACY_UNKNOWN', 'NOT_APPLICABLE')",
        )
        batch_op.create_index(
            "ix_resource_requirements_approval_revision_id",
            ["approval_revision_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_resource_requirements_approved_entry_key",
            ["approved_entry_key"],
            unique=False,
        )
        batch_op.create_index(
            "ix_resource_requirements_approval_reference_status",
            ["approval_reference_status"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            INSERT INTO request_approval_references (
                workforce_request_id,
                active_revision_id,
                status,
                created_at,
                updated_at
            )
            SELECT id, NULL, 'LEGACY_UNKNOWN', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM workforce_requests
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_requirements
            SET approval_reference_status = 'NOT_APPLICABLE'
            WHERE origin IN ('QUICK_SHIFT', 'AD_HOC')
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("resource_requirements") as batch_op:
        batch_op.drop_index("ix_resource_requirements_approval_reference_status")
        batch_op.drop_index("ix_resource_requirements_approved_entry_key")
        batch_op.drop_index("ix_resource_requirements_approval_revision_id")
        batch_op.drop_constraint(
            "fk_resource_requirements_approval_revision_id_request_approval_revisions",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_resource_requirements_resource_requirement_approval_reference_status",
            type_="check",
        )
        batch_op.drop_column("approval_reference_status")
        batch_op.drop_column("approved_entry_key")
        batch_op.drop_column("approval_revision_id")

    op.drop_index(
        "ix_request_approval_reference_active_revision",
        table_name="request_approval_references",
    )
    op.drop_table("request_approval_references")
    op.drop_index(
        "ix_request_approval_revision_fingerprint",
        table_name="request_approval_revisions",
    )
    op.drop_index(
        "ix_request_approval_revision_request_created",
        table_name="request_approval_revisions",
    )
    op.drop_index(
        "ix_request_approval_revisions_previous_revision_id",
        table_name="request_approval_revisions",
    )
    op.drop_index(
        "ix_request_approval_revisions_workforce_request_id",
        table_name="request_approval_revisions",
    )
    op.drop_table("request_approval_revisions")

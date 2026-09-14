"""Add local users mapped to external identities.

Revision ID: 0010_app_users_identity
Revises: 0009_requirement_creator_name
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0010_app_users_identity"
down_revision: str | None = "0009_requirement_creator_name"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "app_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_users")),
        sa.UniqueConstraint("issuer", "subject", name="uq_app_users_issuer_subject"),
    )
    op.create_index(op.f("ix_app_users_issuer"), "app_users", ["issuer"], unique=False)
    op.create_index(op.f("ix_app_users_subject"), "app_users", ["subject"], unique=False)
    op.create_index(op.f("ix_app_users_active"), "app_users", ["active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_users_active"), table_name="app_users")
    op.drop_index(op.f("ix_app_users_subject"), table_name="app_users")
    op.drop_index(op.f("ix_app_users_issuer"), table_name="app_users")
    op.drop_table("app_users")

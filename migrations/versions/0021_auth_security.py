"""Harden OIDC login correlation and session CSRF.

Revision ID: 0021_auth_security
Revises: 0020_competency_catalog
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0021_auth_security"
down_revision: str | None = "0020_competency_catalog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("auth_login_transactions") as batch_op:
        batch_op.add_column(
            sa.Column("browser_binding_hash", sa.String(length=64), nullable=True)
        )
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("csrf_token_hash", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.drop_column("csrf_token_hash")
    with op.batch_alter_table("auth_login_transactions") as batch_op:
        batch_op.drop_column("browser_binding_hash")

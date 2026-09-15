"""Add OIDC login transactions and server-side sessions.

Revision ID: 0011_oidc_sessions
Revises: 0010_app_users_identity
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0011_oidc_sessions"
down_revision: str | None = "0010_app_users_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "auth_login_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=255), nullable=False),
        sa.Column("code_verifier", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_login_transactions")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_auth_login_transactions_state_hash")),
    )
    op.create_index(op.f("ix_auth_login_transactions_state_hash"), "auth_login_transactions", ["state_hash"], unique=True)
    op.create_index(op.f("ix_auth_login_transactions_expires_at"), "auth_login_transactions", ["expires_at"], unique=False)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["app_users.id"], name=op.f("fk_auth_sessions_user_id_app_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index(op.f("ix_auth_sessions_token_hash"), "auth_sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_auth_sessions_expires_at"), "auth_sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_token_hash"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(op.f("ix_auth_login_transactions_expires_at"), table_name="auth_login_transactions")
    op.drop_index(op.f("ix_auth_login_transactions_state_hash"), table_name="auth_login_transactions")
    op.drop_table("auth_login_transactions")

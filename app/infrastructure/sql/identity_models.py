from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_id


class AppUser(TimestampMixin, Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_app_users_issuer_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true(), index=True)

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_id


ID_LENGTH = 36


class BusinessContact(TimestampMixin, Base):
    """Canonical business person/contact, independent from authentication and planning resources."""

    __tablename__ = "business_contacts"
    __table_args__ = (
        CheckConstraint(
            "external_id IS NULL OR "
            "(external_system IS NOT NULL AND external_entity IS NOT NULL)",
            name="business_contact_external_identity_complete",
        ),
        CheckConstraint(
            "version >= 1",
            name="business_contact_version_positive",
        ),
        Index(
            "ux_business_contacts_ext_identity",
            "external_system",
            "external_entity",
            "external_id",
            unique=True,
            sqlite_where=text("external_id IS NOT NULL"),
            postgresql_where=text("external_id IS NOT NULL"),
            mssql_where=text("external_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(ID_LENGTH), primary_key=True, default=new_id
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true(), index=True
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'LOCAL'"), index=True
    )
    external_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

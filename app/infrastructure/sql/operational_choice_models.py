from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin
from .models import ID_LENGTH


class RequestOperationalState(TimestampMixin, Base):
    """Versioned operational choices applied to one active approved revision."""

    __tablename__ = "request_operational_states"
    __table_args__ = (
        CheckConstraint(
            "version >= 1",
            name="request_operational_state_version_positive",
        ),
    )

    workforce_request_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey(
            "workforce_requests.id",
            name="fk_request_operational_states_request",
        ),
        primary_key=True,
    )
    approval_revision_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey(
            "request_approval_revisions.id",
            name="fk_request_operational_states_revision",
        ),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    selections_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'{}'"),
    )
    confirmations_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'{}'"),
    )
    updated_by_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

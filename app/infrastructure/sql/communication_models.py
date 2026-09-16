from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_id


ID_LENGTH = 36


class CommunicationContact(TimestampMixin, Base):
    __tablename__ = "communication_contacts"
    __table_args__ = (
        Index("ux_communication_contacts_recipient", "recipient_id", unique=True),
        Index("ix_communication_contacts_audience_active", "audience", "active"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    recipient_id: Mapped[str] = mapped_column(String(180), nullable=False)
    audience: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())


class CommunicationBatchRow(Base):
    __tablename__ = "communication_batches"
    __table_args__ = (
        Index("ix_communication_batches_week_status", "week_start", "status"),
        Index(
            "ix_communication_batches_fingerprint",
            "week_start",
            "kind",
            "snapshot_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    prepared_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prepared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    communicated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    communicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunicationMessageRow(Base):
    __tablename__ = "communication_messages"
    __table_args__ = (Index("ix_communication_messages_batch", "batch_id", "audience"),)

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("communication_batches.id", ondelete="CASCADE"), nullable=False
    )
    audience: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(180), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())


class CommunicationSnapshotLine(Base):
    __tablename__ = "communication_snapshot_lines"
    __table_args__ = (Index("ix_communication_snapshot_batch", "batch_id", "day"),)

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("communication_batches.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(180), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_manager_id: Mapped[str] = mapped_column(String(180), nullable=False, server_default="")
    project_number: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    project_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    day: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    allocation_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="Flexible")
    outside_schedule: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmation: Mapped[str] = mapped_column(String(32), nullable=False, server_default="Confirmée")

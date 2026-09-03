from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_id
from .models import ID_LENGTH


class WorkforceRequestPeriod(TimestampMixin, Base):
    """Versioned requested period that may later materialize into a requirement."""

    __tablename__ = "workforce_request_periods"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="request_period_date_window"),
        CheckConstraint("hours > 0", name="request_period_hours_positive"),
        CheckConstraint("resource_count >= 1", name="request_period_resource_count"),
        CheckConstraint(
            "(kind = 'ALTERNATIVE' AND alternative_group IS NOT NULL) OR "
            "(kind = 'CUMULATIVE' AND alternative_group IS NULL)",
            name="request_period_kind_group_consistency",
        ),
        Index(
            "ix_request_periods_request_kind_group",
            "workforce_request_id",
            "kind",
            "alternative_group",
        ),
        Index(
            "ix_request_periods_request_active",
            "workforce_request_id",
            "active",
        ),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    workforce_request_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("workforce_requests.id"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'CUMULATIVE'"), index=True
    )
    alternative_group: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    confirmation: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'Tentative'"), index=True
    )
    proposed_resource_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), ForeignKey("resources.id"), nullable=True, index=True
    )
    resource_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true(), index=True)


class WorkforceRequestPeriodSelection(Base):
    """Single selected option for one exclusive group of one workforce request."""

    __tablename__ = "workforce_request_period_selections"
    __table_args__ = (
        Index("ix_request_period_selection_period", "period_id"),
    )

    workforce_request_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("workforce_requests.id"),
        primary_key=True,
    )
    alternative_group: Mapped[str] = mapped_column(String(64), primary_key=True)
    period_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("workforce_request_periods.id"),
        nullable=False,
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    selected_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

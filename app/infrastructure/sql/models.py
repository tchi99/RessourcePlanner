from __future__ import annotations

from datetime import date, datetime, time
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
    Time,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_id


ID_LENGTH = 36
ORIGIN_REQUEST = "REQUEST"
ORIGIN_QUICK_SHIFT = "QUICK_SHIFT"
ORIGIN_AD_HOC = "AD_HOC"


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    erp_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''"))
    client: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_manager_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    project_manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"), index=True)


class Resource(TimestampMixin, Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    resource_class: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true(), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class WorkPackage(TimestampMixin, Base):
    __tablename__ = "work_packages"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="work_package_date_window",
        ),
        CheckConstraint(
            "planned_hours IS NULL OR planned_hours >= 0",
            name="work_package_hours_non_negative",
        ),
        Index("ix_work_packages_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("projects.id"), nullable=False, index=True
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'planned'"), index=True)
    legacy_effort_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)


class WorkforceRequest(TimestampMixin, Base):
    __tablename__ = "workforce_requests"
    __table_args__ = (
        CheckConstraint("resource_count >= 1", name="workforce_request_resource_count"),
        CheckConstraint(
            "desired_end IS NULL OR desired_start IS NULL OR desired_end >= desired_start",
            name="workforce_request_date_window",
        ),
        CheckConstraint(
            "estimated_hours IS NULL OR estimated_hours >= 0",
            name="workforce_request_hours_non_negative",
        ),
        CheckConstraint(
            "estimated_days IS NULL OR estimated_days >= 0",
            name="workforce_request_days_non_negative",
        ),
        Index("ix_workforce_requests_project_status", "project_id", "status"),
        Index("ix_workforce_requests_window", "desired_start", "desired_end"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    legacy_demand_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("projects.id"), nullable=False, index=True
    )
    # Nullable only for migration of current V1 requests that predate WorkPackages.
    work_package_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), ForeignKey("work_packages.id"), nullable=True, index=True
    )
    requester_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requester_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'Projet'"))
    priority: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'Normale'"), index=True)
    confirmation: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'Confirmée'"), index=True)
    desired_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    desired_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_client: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    required_competencies: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    estimated_days: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    proposed_resource_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), ForeignKey("resources.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'Brouillon'"), index=True)
    approved_by_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkforceRequestHistory(Base):
    __tablename__ = "workforce_request_history"
    __table_args__ = (
        Index("ix_workforce_request_history_request_time", "workforce_request_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    workforce_request_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("workforce_requests.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResourceAvailabilityRule(TimestampMixin, Base):
    __tablename__ = "resource_availability_rules"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="availability_date_window",
        ),
        Index("ix_availability_resource_window", "resource_id", "start_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    legacy_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    resource_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("resources.id"), nullable=False, index=True
    )
    availability_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekdays: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true(), index=True)


class ResourceRequirement(TimestampMixin, Base):
    __tablename__ = "resource_requirements"
    __table_args__ = (
        CheckConstraint("planned_hours > 0", name="resource_requirement_hours_positive"),
        CheckConstraint("end_date >= start_date", name="resource_requirement_date_window"),
        CheckConstraint(
            "workforce_request_id IS NOT NULL OR origin IN ('QUICK_SHIFT', 'AD_HOC')",
            name="resource_requirement_request_or_adhoc",
        ),
        Index("ix_resource_requirements_project_window", "project_id", "start_date", "end_date"),
        Index("ix_resource_requirements_resource_window", "assigned_resource_id", "start_date", "end_date"),
        Index("ix_resource_requirements_request_status", "workforce_request_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    legacy_segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("projects.id"), nullable=False, index=True
    )
    workforce_request_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), ForeignKey("workforce_requests.id"), nullable=True, index=True
    )
    assigned_resource_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), ForeignKey("resources.id"), nullable=True, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'À assigner'"), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_effort_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    required_competency: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    planning_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'Flexible'"), index=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'Normale'"), index=True)
    outside_standard_hours_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'REQUEST'"), index=True)
    created_by_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Shift(TimestampMixin, Base):
    __tablename__ = "shifts"
    __table_args__ = (
        CheckConstraint("hours > 0", name="shift_hours_positive"),
        Index("ix_shifts_resource_date", "resource_id", "work_date"),
        Index("ix_shifts_requirement_date", "resource_requirement_id", "work_date"),
        Index("ix_shifts_locked_date", "locked", "work_date"),
    )

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)
    legacy_allocation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_requirement_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("resource_requirements.id"), nullable=False, index=True
    )
    resource_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), ForeignKey("resources.id"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    allocation_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'AUTO'"), index=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false(), index=True)
    outside_standard_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    confirmation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

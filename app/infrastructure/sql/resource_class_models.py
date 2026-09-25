from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


RESOURCE_CLASS_CODE_LENGTH = 64
TASK_CODE_LENGTH = 64
PROJECT_ID_LENGTH = 36


class ResourceClassConfig(TimestampMixin, Base):
    __tablename__ = "resource_class_configs"
    __table_args__ = (
        CheckConstraint(
            "version >= 1",
            name="resource_class_config_version_positive",
        ),
    )

    code: Mapped[str] = mapped_column(
        String(RESOURCE_CLASS_CODE_LENGTH),
        primary_key=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    average_hourly_cost_cad: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )


class TaskClassStandard(TimestampMixin, Base):
    __tablename__ = "task_class_standards"
    __table_args__ = (
        CheckConstraint(
            "version >= 1",
            name="task_class_standard_version_positive",
        ),
    )

    task_code: Mapped[str] = mapped_column(
        String(TASK_CODE_LENGTH),
        primary_key=True,
    )
    resource_class_code: Mapped[str] = mapped_column(
        String(RESOURCE_CLASS_CODE_LENGTH),
        nullable=False,
        index=True,
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )


class ProjectTaskClassOverride(TimestampMixin, Base):
    __tablename__ = "project_task_class_overrides"
    __table_args__ = (
        CheckConstraint(
            "version >= 1",
            name="project_task_class_override_version_positive",
        ),
        CheckConstraint(
            "excluded = 1 OR resource_class_code IS NOT NULL",
            name="project_task_class_override_value_required",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        String(PROJECT_ID_LENGTH),
        ForeignKey("projects.id"),
        primary_key=True,
    )
    task_code: Mapped[str] = mapped_column(
        String(TASK_CODE_LENGTH),
        primary_key=True,
    )
    resource_class_code: Mapped[str | None] = mapped_column(
        String(RESOURCE_CLASS_CODE_LENGTH),
        nullable=True,
        index=True,
    )
    excluded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )

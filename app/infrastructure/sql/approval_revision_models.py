from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_id
from .models import ID_LENGTH


APPROVAL_REFERENCE_CAPTURED = "CAPTURED"
APPROVAL_REFERENCE_LEGACY_UNKNOWN = "LEGACY_UNKNOWN"
APPROVAL_REFERENCE_NOT_APPLICABLE = "NOT_APPLICABLE"
APPROVAL_REFERENCE_STATUSES = {
    APPROVAL_REFERENCE_CAPTURED,
    APPROVAL_REFERENCE_LEGACY_UNKNOWN,
    APPROVAL_REFERENCE_NOT_APPLICABLE,
}


class RequestApprovalRevision(TimestampMixin, Base):
    """Immutable proof of one approved workforce-request authorization."""

    __tablename__ = "request_approval_revisions"
    __table_args__ = (
        CheckConstraint(
            "request_version >= 1",
            name="req_version_positive",
        ),
        CheckConstraint(
            "payload_format_version >= 1",
            name="format_version_positive",
        ),
        Index(
            "ix_request_approval_revision_request_created",
            "workforce_request_id",
            "created_at",
        ),
        Index(
            "ix_request_approval_revision_fingerprint",
            "authorization_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        primary_key=True,
        default=new_id,
    )
    workforce_request_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("workforce_requests.id", name="fk_req_approval_revisions_request"),
        nullable=False,
        index=True,
    )
    previous_revision_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("request_approval_revisions.id", name="fk_req_approval_revisions_previous"),
        nullable=True,
        index=True,
    )
    request_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by_external_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    approved_by_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    provenance: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'APPROVAL'"),
    )
    payload_format_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    payload_text: Mapped[str] = mapped_column(Text, nullable=False)
    authorization_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )


class RequestApprovalReference(TimestampMixin, Base):
    """Mutable head pointing to the immutable authorization currently in force."""

    __tablename__ = "request_approval_references"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CAPTURED', 'LEGACY_UNKNOWN')",
            name="status",
        ),
        Index(
            "ix_request_approval_reference_active_revision",
            "active_revision_id",
        ),
    )

    workforce_request_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("workforce_requests.id", name="fk_req_approval_refs_request"),
        primary_key=True,
    )
    active_revision_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("request_approval_revisions.id", name="fk_req_approval_refs_active_revision"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'LEGACY_UNKNOWN'"),
    )

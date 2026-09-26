from __future__ import annotations

from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ErpUserDirectoryEntry(TimestampMixin, Base):
    __tablename__ = "erp_user_directory"

    # Stable Acumatica RP_Users.UserID. This is deliberately not an OIDC subject.
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Logical relation to RP_Employees.EmployeID / Resource.external_id.
    employee_external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    erp_user_active: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    employee_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Local authorization configuration. Synchronization never overwrites these.
    local_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), index=True
    )
    roles_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )

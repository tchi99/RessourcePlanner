from __future__ import annotations

from sqlalchemy.orm import Session

from ...application.smtp_settings import (
    SmtpConfigurationStored,
)
from .base import utc_now
from .communication_models import SmtpConfigurationRow


class SqlSmtpConfigurationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_smtp_configuration(self) -> SmtpConfigurationStored | None:
        row = self._session.get(SmtpConfigurationRow, "smtp")
        if row is None:
            return None
        return SmtpConfigurationStored(
            host=row.host,
            port=int(row.port),
            security=row.security,
            username=row.username,
            encrypted_password=row.encrypted_password,
            from_email=row.from_email,
            from_name=row.from_name,
            reply_to=row.reply_to,
            timeout_seconds=int(row.timeout_seconds),
            enabled=bool(row.enabled),
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    def save_smtp_configuration(
        self,
        *,
        configuration: SmtpConfigurationStored,
        actor_name: str,
    ) -> SmtpConfigurationStored:
        row = self._session.get(SmtpConfigurationRow, "smtp")
        if row is None:
            row = SmtpConfigurationRow(id="smtp")
            self._session.add(row)

        row.host = configuration.host
        row.port = int(configuration.port)
        row.security = configuration.security
        row.username = configuration.username
        row.encrypted_password = configuration.encrypted_password
        row.from_email = configuration.from_email
        row.from_name = configuration.from_name
        row.reply_to = configuration.reply_to
        row.timeout_seconds = int(configuration.timeout_seconds)
        row.enabled = bool(configuration.enabled)
        row.updated_by = str(actor_name or "").strip() or None
        row.updated_at = utc_now()
        self._session.flush()
        return self.get_smtp_configuration() or configuration

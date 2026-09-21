from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ...application.smtp_settings import (
    SmtpConfigurationStored,
)
from .base import utc_now
from .communication_models import (
    SmtpConfigurationAuditRow,
    SmtpConfigurationRow,
)


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
        created = row is None
        if row is None:
            row = SmtpConfigurationRow(id="smtp")
            self._session.add(row)

        before = {
            "host": row.host,
            "port": int(row.port or 587),
            "security": row.security,
            "username": row.username,
            "credential": bool(row.encrypted_password),
            "from_email": row.from_email,
            "from_name": row.from_name,
            "reply_to": row.reply_to,
            "timeout_seconds": int(row.timeout_seconds or 20),
            "enabled": bool(row.enabled),
        }
        after = {
            "host": configuration.host,
            "port": int(configuration.port),
            "security": configuration.security,
            "username": configuration.username,
            "credential": bool(configuration.encrypted_password),
            "from_email": configuration.from_email,
            "from_name": configuration.from_name,
            "reply_to": configuration.reply_to,
            "timeout_seconds": int(configuration.timeout_seconds),
            "enabled": bool(configuration.enabled),
        }
        changed_fields = [
            field
            for field in after
            if created or before[field] != after[field]
        ]
        if (
            not created
            and row.encrypted_password != configuration.encrypted_password
            and "credential" not in changed_fields
        ):
            changed_fields.append("credential")

        actor = str(actor_name or "").strip() or None
        now = utc_now()
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
        row.updated_by = actor
        row.updated_at = now

        self._session.add(
            SmtpConfigurationAuditRow(
                event_type="SMTP_CONFIG_UPDATED",
                actor_name=actor,
                changed_fields_json=json.dumps(
                    sorted(changed_fields),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                created_at=now,
            )
        )
        self._session.flush()
        return self.get_smtp_configuration() or configuration

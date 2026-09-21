from __future__ import annotations

from email.message import EmailMessage
import smtplib
import ssl

from cryptography.fernet import Fernet

from ..application.communications import CommunicationTransportMessage
from ..application.smtp_settings import (
    SMTP_SECURITY_SSL_TLS,
    SmtpRuntimeConfiguration,
)


class FernetSecretCipher:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(str(key).strip().encode("ascii"))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(str(value).encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(str(value).encode("ascii")).decode("utf-8")


class SmtpClient:
    @staticmethod
    def _connect(configuration: SmtpRuntimeConfiguration):
        timeout = float(configuration.timeout_seconds)
        if configuration.security == SMTP_SECURITY_SSL_TLS:
            return smtplib.SMTP_SSL(
                configuration.host,
                configuration.port,
                timeout=timeout,
                context=ssl.create_default_context(),
            )
        client = smtplib.SMTP(
            configuration.host,
            configuration.port,
            timeout=timeout,
        )
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        return client

    @staticmethod
    def _login(client, configuration: SmtpRuntimeConfiguration) -> None:
        if configuration.username:
            client.login(
                configuration.username,
                configuration.password or "",
            )

    def test_connection(self, configuration: SmtpRuntimeConfiguration) -> None:
        with self._connect(configuration) as client:
            self._login(client, configuration)
            client.noop()

    def send_message(
        self,
        configuration: SmtpRuntimeConfiguration,
        message: CommunicationTransportMessage,
        *,
        message_id: str,
    ) -> str:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = (
            f"{configuration.from_name} <{configuration.from_email}>"
            if configuration.from_name
            else configuration.from_email
        )
        email["To"] = message.recipient_email
        if message.cc_emails:
            email["Cc"] = ", ".join(message.cc_emails)
        if configuration.reply_to:
            email["Reply-To"] = configuration.reply_to
        email["Message-ID"] = message_id
        email.set_content(message.body)

        with self._connect(configuration) as client:
            self._login(client, configuration)
            client.send_message(email)
        return message_id

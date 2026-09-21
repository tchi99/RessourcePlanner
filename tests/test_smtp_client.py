from __future__ import annotations

import unittest
from unittest.mock import patch

from app.application.communications import CommunicationTransportMessage
from app.application.smtp_settings import (
    SMTP_SECURITY_SSL_TLS,
    SMTP_SECURITY_STARTTLS,
    SmtpRuntimeConfiguration,
)
from app.infrastructure.smtp import SmtpClient


TEST_DOMAIN = "example.test"


class FakeSmtpConnection:
    def __init__(self) -> None:
        self.ehlo_count = 0
        self.starttls_count = 0
        self.login_calls = []
        self.sent_messages = []
        self.noop_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        self.ehlo_count += 1

    def starttls(self, *, context):
        self.starttls_count += 1

    def login(self, username, credential):
        self.login_calls.append((username, credential))

    def noop(self):
        self.noop_count += 1

    def send_message(self, message):
        self.sent_messages.append(message)


class SmtpClientTests(unittest.TestCase):
    @staticmethod
    def _configuration(security: str) -> SmtpRuntimeConfiguration:
        return SmtpRuntimeConfiguration(
            host="smtp.example.invalid",
            port=587 if security == SMTP_SECURITY_STARTTLS else 465,
            security=security,
            username="mailer",
            credential="fixture-" + "credential",
            from_email="planning" + chr(64) + TEST_DOMAIN,
            from_name="RessourcePlanner",
            reply_to="reply" + chr(64) + TEST_DOMAIN,
            timeout_seconds=20,
        )

    @staticmethod
    def _message() -> CommunicationTransportMessage:
        return CommunicationTransportMessage(
            audience="project",
            recipient_id="project:P1",
            recipient_email="pm" + chr(64) + TEST_DOMAIN,
            subject="Confirmation projet",
            body="Bonjour\nPlanning confirmé.",
            cc_emails=(
                "tech-a" + chr(64) + TEST_DOMAIN,
                "tech-b" + chr(64) + TEST_DOMAIN,
            ),
        )

    def test_starttls_send_builds_expected_headers_and_authenticates(self) -> None:
        connection = FakeSmtpConnection()
        with patch("app.infrastructure.smtp.smtplib.SMTP", return_value=connection):
            result = SmtpClient().send_message(
                self._configuration(SMTP_SECURITY_STARTTLS),
                self._message(),
                message_id="<fixture-message" + chr(64) + "local.invalid>",
            )

        self.assertEqual(result, "<fixture-message" + chr(64) + "local.invalid>")
        self.assertEqual(connection.starttls_count, 1)
        self.assertEqual(connection.ehlo_count, 2)
        self.assertEqual(
            connection.login_calls,
            [("mailer", "fixture-" + "credential")],
        )
        self.assertEqual(len(connection.sent_messages), 1)
        sent = connection.sent_messages[0]
        self.assertEqual(sent["To"], "pm" + chr(64) + TEST_DOMAIN)
        self.assertIn("tech-a" + chr(64) + TEST_DOMAIN, sent["Cc"])
        self.assertIn("tech-b" + chr(64) + TEST_DOMAIN, sent["Cc"])
        self.assertEqual(sent["Reply-To"], "reply" + chr(64) + TEST_DOMAIN)
        self.assertEqual(
            sent["Message-ID"],
            "<fixture-message" + chr(64) + "local.invalid>",
        )

    def test_ssl_tls_uses_smtp_ssl_and_connection_test_does_not_send(self) -> None:
        connection = FakeSmtpConnection()
        with patch(
            "app.infrastructure.smtp.smtplib.SMTP_SSL",
            return_value=connection,
        ) as smtp_ssl:
            SmtpClient().test_connection(
                self._configuration(SMTP_SECURITY_SSL_TLS)
            )

        smtp_ssl.assert_called_once()
        self.assertEqual(connection.starttls_count, 0)
        self.assertEqual(connection.noop_count, 1)
        self.assertEqual(connection.sent_messages, [])


if __name__ == "__main__":
    unittest.main()

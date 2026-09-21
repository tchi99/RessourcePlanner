from __future__ import annotations

from cryptography.fernet import Fernet
import unittest

from app.application.errors import ApplicationUnavailableError
from app.application.smtp_settings import (
    SMTP_SECURITY_STARTTLS,
    SmtpConfigurationService,
    SmtpConfigurationUpdate,
)
from app.infrastructure.smtp import FernetSecretCipher
from app.infrastructure.sql import (
    Base,
    SmtpConfigurationAuditRow,
    SmtpConfigurationRow,
    SqlSmtpConfigurationRepository,
    create_session_factory,
    create_sql_engine,
)


TEST_DOMAIN = "example.test"


class FakeSmtpClient:
    def __init__(self) -> None:
        self.tested = []
        self.sent = []

    def test_connection(self, configuration) -> None:
        self.tested.append(configuration)

    def send_message(self, configuration, message, *, message_id: str) -> str:
        self.sent.append((configuration, message, message_id))
        return message_id


class SmtpConfigurationTests(unittest.TestCase):
    def _factory(self):
        engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        return engine, create_session_factory(engine)

    def test_password_is_encrypted_at_rest_and_never_returned(self) -> None:
        engine, factory = self._factory()
        secret_value = "smtp-" + "test-secret"
        key = Fernet.generate_key().decode("ascii")
        cipher = FernetSecretCipher(key)
        fake = FakeSmtpClient()
        try:
            with factory.begin() as session:
                service = SmtpConfigurationService(
                    SqlSmtpConfigurationRepository(session),
                    cipher=cipher,
                    client=fake,
                )
                view = service.update(
                    SmtpConfigurationUpdate(
                        host="smtp.example.invalid",
                        port=587,
                        security=SMTP_SECURITY_STARTTLS,
                        username="mailer",
                        credential=secret_value,
                        clear_password=False,
                        from_email="planning" + chr(64) + TEST_DOMAIN,
                        from_name="RessourcePlanner",
                        reply_to=None,
                        timeout_seconds=20,
                        enabled=True,
                    ),
                    actor_name="Admin test",
                )
                self.assertTrue(view.password_configured)
                self.assertTrue(view.encryption_available)
                self.assertFalse(hasattr(view, "password"))

                row = session.get(SmtpConfigurationRow, "smtp")
                assert row is not None
                self.assertIsNotNone(row.encrypted_password)
                self.assertNotEqual(row.encrypted_password, secret_value)
                self.assertEqual(cipher.decrypt(row.encrypted_password or ""), secret_value)

                audits = session.query(SmtpConfigurationAuditRow).all()
                self.assertEqual(len(audits), 1)
                self.assertEqual(audits[0].event_type, "SMTP_CONFIG_UPDATED")
                self.assertEqual(audits[0].actor_name, "Admin test")
                self.assertIn("credential", audits[0].changed_fields_json)
                self.assertNotIn(secret_value, audits[0].changed_fields_json)
                self.assertNotIn(row.encrypted_password or "", audits[0].changed_fields_json)

                service.test_connection()
                self.assertEqual(len(fake.tested), 1)
                self.assertEqual(fake.tested[0].credential, secret_value)
        finally:
            engine.dispose()

    def test_password_update_requires_server_encryption_key(self) -> None:
        engine, factory = self._factory()
        try:
            with factory.begin() as session:
                service = SmtpConfigurationService(
                    SqlSmtpConfigurationRepository(session),
                    cipher=None,
                    client=FakeSmtpClient(),
                )
                with self.assertRaises(ApplicationUnavailableError) as caught:
                    service.update(
                        SmtpConfigurationUpdate(
                            host="smtp.example.invalid",
                            port=587,
                            security=SMTP_SECURITY_STARTTLS,
                            username="mailer",
                            credential="smtp-" + "secret",
                            clear_password=False,
                            from_email="planning" + chr(64) + TEST_DOMAIN,
                            from_name=None,
                            reply_to=None,
                            timeout_seconds=20,
                            enabled=True,
                        ),
                        actor_name="Admin test",
                    )
                self.assertEqual(caught.exception.code, "smtp_encryption_key_unavailable")
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()

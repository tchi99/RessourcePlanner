from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.application.security import AuthPrincipal, ROLE_COORDINATOR
from app.application.smtp_settings import SmtpConnectionTestResult, SmtpTestLogEntry
from app.infrastructure.smtp import FernetSecretCipher
from app.infrastructure.sql import Base, create_sql_engine
from app.server import create_api_app
from app.server.security import static_auth_resolver
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER


TEST_DOMAIN = "example.test"


class FailingDiagnosticSmtpClient:
    def test_connection(self, configuration):
        return SmtpConnectionTestResult(
            ok=False,
            message="Échec du test SMTP à l'étape « authentification ».",
            log=(
                SmtpTestLogEntry(
                    level="INFO",
                    step="connexion",
                    message="Connexion TCP établie.",
                ),
                SmtpTestLogEntry(
                    level="ERROR",
                    step="authentification",
                    message="SMTP 535: Authentication failed",
                ),
            ),
        )

    def send_message(self, configuration, message, *, message_id: str) -> str:
        return message_id


class FakeSmtpClient:
    def __init__(self) -> None:
        self.tested = []
        self.sent = []

    def test_connection(self, configuration) -> None:
        self.tested.append(configuration)

    def send_message(self, configuration, message, *, message_id: str) -> str:
        self.sent.append((configuration, message, message_id))
        return message_id


def coordinator_resolver():
    return static_auth_resolver(
        AuthPrincipal.from_roles(
            local_user_id="coord-test",
            issuer="urn:test",
            subject="coord",
            display_name="Coordonnateur test",
            email=None,
            roles=(ROLE_COORDINATOR,),
            auth_mode="test",
        )
    )


class ServerSmtpSettingsTests(unittest.TestCase):
    @staticmethod
    def _database(directory: str) -> str:
        path = Path(directory) / "smtp-settings.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        engine.dispose()
        return url

    def test_admin_can_configure_and_test_without_secret_echo(self) -> None:
        with TemporaryDirectory() as directory:
            fake = FakeSmtpClient()
            cipher = FernetSecretCipher(Fernet.generate_key().decode("ascii"))
            app = create_api_app(
                self._database(directory),
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
                smtp_cipher=cipher,
                smtp_client=fake,
            )
            secret_value = "smtp-" + "api-secret"
            with TestClient(app) as client:
                response = client.put(
                    "/api/v1/admin/settings/smtp",
                    json={
                        "host": "smtp.example.invalid",
                        "port": 587,
                        "security": "STARTTLS",
                        "username": "mailer",
                        "password": secret_value,
                        "clear_password": False,
                        "from_email": "planning" + chr(64) + TEST_DOMAIN,
                        "from_name": "RessourcePlanner",
                        "reply_to": None,
                        "timeout_seconds": 20,
                        "enabled": True,
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload["password_configured"])
                self.assertTrue(payload["encryption_available"])
                self.assertNotIn("password", payload)
                self.assertNotIn("encrypted_password", payload)
                self.assertNotIn(secret_value, response.text)

                test_response = client.post("/api/v1/admin/settings/smtp/test")
                self.assertEqual(test_response.status_code, 200, test_response.text)
                self.assertTrue(test_response.json()["ok"])

            self.assertEqual(len(fake.tested), 1)
            self.assertEqual(fake.tested[0].credential, secret_value)

    def test_admin_can_send_test_email_when_general_smtp_is_disabled(self) -> None:
        with TemporaryDirectory() as directory:
            fake = FakeSmtpClient()
            app = create_api_app(
                self._database(directory),
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
                smtp_client=fake,
            )
            recipient = "recipient" + chr(64) + TEST_DOMAIN
            with TestClient(app) as client:
                configured = client.put(
                    "/api/v1/admin/settings/smtp",
                    json={
                        "host": "smtp.example.invalid",
                        "port": 587,
                        "security": "STARTTLS",
                        "username": None,
                        "password": None,
                        "clear_password": False,
                        "from_email": "planning" + chr(64) + TEST_DOMAIN,
                        "from_name": "RessourcePlanner",
                        "reply_to": None,
                        "timeout_seconds": 20,
                        "enabled": False,
                    },
                )
                self.assertEqual(configured.status_code, 200, configured.text)

                response = client.post(
                    "/api/v1/admin/settings/smtp/test-email",
                    json={"recipient_email": recipient},
                )
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["log"][-1]["step"], "envoi")

            self.assertEqual(len(fake.sent), 1)
            _configuration, message, message_id = fake.sent[0]
            self.assertEqual(message.recipient_email, recipient)
            self.assertEqual(message.subject, "Test SMTP — RessourcePlanner")
            self.assertIn("Ceci est un courriel de test", message.body)
            self.assertTrue(message_id.startswith("<resourceplanner-smtp-test-"))

    def test_failed_smtp_test_returns_diagnostic_log_without_http_error(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
                smtp_client=FailingDiagnosticSmtpClient(),
            )
            with TestClient(app) as client:
                configured = client.put(
                    "/api/v1/admin/settings/smtp",
                    json={
                        "host": "smtp.example.invalid",
                        "port": 587,
                        "security": "STARTTLS",
                        "username": None,
                        "password": None,
                        "clear_password": False,
                        "from_email": "planning" + chr(64) + TEST_DOMAIN,
                        "from_name": "RessourcePlanner",
                        "reply_to": None,
                        "timeout_seconds": 20,
                        "enabled": False,
                    },
                )
                self.assertEqual(configured.status_code, 200, configured.text)

                response = client.post("/api/v1/admin/settings/smtp/test")
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["log"][-1]["level"], "ERROR")
                self.assertEqual(payload["log"][-1]["step"], "authentification")
                self.assertIn("SMTP 535", payload["log"][-1]["message"])
                self.assertNotIn("password", response.text.lower())

    def test_coordinator_cannot_read_or_change_admin_settings(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                auth_resolver=coordinator_resolver(),
                smtp_client=FakeSmtpClient(),
            )
            with TestClient(app) as client:
                response = client.get("/api/v1/admin/settings/smtp")
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(
                    response.json()["error"]["context"]["required_permission"],
                    "admin_settings",
                )

                update = client.put(
                    "/api/v1/admin/settings/smtp",
                    json={
                        "host": "smtp.example.invalid",
                        "port": 587,
                        "security": "STARTTLS",
                        "username": None,
                        "password": None,
                        "clear_password": False,
                        "from_email": "planning" + chr(64) + TEST_DOMAIN,
                        "from_name": None,
                        "reply_to": None,
                        "timeout_seconds": 20,
                        "enabled": False,
                    },
                )
                self.assertEqual(update.status_code, 403, update.text)


if __name__ == "__main__":
    unittest.main()

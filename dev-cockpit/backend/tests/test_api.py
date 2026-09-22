from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class ApiTests(unittest.TestCase):
    def test_health_and_config_never_expose_token_value(self):
        secret = "test"
        client = TestClient(create_app(Settings(github_token=secret)))
        health = client.get("/api/health")
        config = client.get("/api/config")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(config.status_code, 200)
        combined = health.text + config.text
        self.assertNotIn(secret, combined)
        self.assertTrue(config.json()["token_configured"])

    def test_dashboard_without_token_returns_useful_configuration_error(self):
        client = TestClient(create_app(Settings(github_token=None)))
        response = client.get("/api/dashboard")
        self.assertEqual(response.status_code, 503)
        self.assertIn("DEV_COCKPIT_GITHUB_TOKEN", response.json()["detail"])
        self.assertEqual(client.get("/api/health").json()["status"], "configuration_error")

    def test_roles_can_be_managed_without_github_token(self):
        with TemporaryDirectory() as temp_dir:
            client = TestClient(
                create_app(Settings(github_token=None, data_dir=temp_dir))
            )
            defaults = client.get("/api/roles")
            self.assertEqual(defaults.status_code, 200)
            self.assertEqual(defaults.json()["roles"][1]["id"], "developer")

            updated = client.put(
                "/api/roles",
                json={
                    "roles": [
                        {
                            "id": "developer",
                            "name": "DEV #13",
                            "avatar": "developer",
                            "chat_url": "https://chatgpt.com/c/example",
                            "enabled": True,
                            "order": 10,
                        }
                    ]
                },
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["roles"][0]["name"], "DEV #13")

            second_client = TestClient(
                create_app(Settings(github_token=None, data_dir=temp_dir))
            )
            persisted = second_client.get("/api/roles")
            self.assertEqual(
                persisted.json()["roles"][0]["chat_url"],
                "https://chatgpt.com/c/example",
            )


if __name__ == "__main__":
    unittest.main()

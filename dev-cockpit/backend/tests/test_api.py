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


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.server import ServerConfigurationError, ServerSettings, create_configured_app


class WebRuntimeTests(unittest.TestCase):
    def _frontend_build(self, root: Path) -> Path:
        dist = root / "dist"
        assets = dist / "assets"
        assets.mkdir(parents=True)
        (dist / "index.html").write_text(
            '<!doctype html><html><body><div id="root"></div>'
            '<script type="module" src="/assets/app.js"></script></body></html>',
            encoding="utf-8",
        )
        (assets / "app.js").write_text("console.log('resourceplanner-web');", encoding="utf-8")
        return dist

    def test_configured_app_serves_frontend_and_keeps_api_namespace(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist = self._frontend_build(Path(temp_dir))
            app = create_configured_app(
                ServerSettings(
                    database_url="sqlite+pysqlite:///:memory:",
                    frontend_dist=str(dist),
                )
            )

            with TestClient(app) as client:
                index = client.get("/")
                self.assertEqual(index.status_code, 200)
                self.assertIn('id="root"', index.text)

                asset = client.get("/assets/app.js")
                self.assertEqual(asset.status_code, 200)
                self.assertIn("resourceplanner-web", asset.text)

                health = client.get("/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["database"], "sqlite")

                missing_api = client.get("/api/v1/not-a-real-route")
                self.assertEqual(missing_api.status_code, 404)
                self.assertIn("application/json", missing_api.headers["content-type"])

    def test_frontend_is_optional_for_api_only_server(self) -> None:
        app = create_configured_app(
            ServerSettings(database_url="sqlite+pysqlite:///:memory:")
        )
        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 404)
            self.assertEqual(client.get("/health").status_code, 200)

    def test_requested_frontend_build_must_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing-dist"
            with self.assertRaises(ServerConfigurationError) as caught:
                create_configured_app(
                    ServerSettings(
                        database_url="sqlite+pysqlite:///:memory:",
                        frontend_dist=str(missing),
                    )
                )
            self.assertIn("Build React introuvable", str(caught.exception))

    def test_environment_can_enable_frontend_build(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist = self._frontend_build(Path(temp_dir))
            settings = ServerSettings.from_environment(
                {
                    "RESOURCEPLANNER_DATABASE_URL": "sqlite+pysqlite:///:memory:",
                    "RESOURCEPLANNER_FRONTEND_DIST": str(dist),
                }
            )
            self.assertEqual(settings.frontend_dist, str(dist))


if __name__ == "__main__":
    unittest.main()

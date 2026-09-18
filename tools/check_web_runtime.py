from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.server import ServerSettings, create_configured_app


ASSET_RE = re.compile(r"(?:src|href)=[\"'](?P<path>/assets/[^\"']+)[\"']")
DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"


def _migrate_temporary_database(database_url: str) -> None:
    previous = os.environ.get(DATABASE_URL_ENV)
    os.environ[DATABASE_URL_ENV] = database_url
    try:
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop(DATABASE_URL_ENV, None)
        else:
            os.environ[DATABASE_URL_ENV] = previous


def _failure(reason: str, **extra: object) -> int:
    print(json.dumps({"status": "failed", "reason": reason, **extra}, sort_keys=True))
    return 1


def main() -> int:
    frontend_dist = ROOT / "frontend" / "dist"

    with TemporaryDirectory() as directory:
        database_path = Path(directory) / "web-runtime.db"
        database_url = f"sqlite:///{database_path.as_posix()}"
        try:
            _migrate_temporary_database(database_url)
            settings = ServerSettings(
                database_url=database_url,
                frontend_dist=str(frontend_dist),
            )
            app = create_configured_app(settings)
        except Exception as exc:  # pragma: no cover - command-line diagnostic path
            return _failure("app_creation_failed", error_type=type(exc).__name__)

        with TestClient(app) as client:
            root = client.get("/")
            if root.status_code != 200 or "text/html" not in root.headers.get("content-type", ""):
                return _failure("frontend_index_failed", http_status=root.status_code)

            match = ASSET_RE.search(root.text)
            if match is None:
                return _failure("frontend_asset_missing")

            asset_path = match.group("path")
            asset = client.get(asset_path)
            if asset.status_code != 200:
                return _failure(
                    "frontend_asset_failed",
                    asset=asset_path,
                    http_status=asset.status_code,
                )

            health = client.get("/health")
            if health.status_code != 200 or health.json().get("status") != "ok":
                return _failure("health_failed", http_status=health.status_code)

            ready = client.get("/ready")
            if ready.status_code != 200 or ready.json().get("status") != "ready":
                return _failure("readiness_failed", http_status=ready.status_code)

            missing_api = client.get("/api/v1/__web_runtime_smoke_missing__")
            if missing_api.status_code != 404:
                return _failure(
                    "unknown_api_not_404",
                    http_status=missing_api.status_code,
                )
            content_type = missing_api.headers.get("content-type", "")
            if "application/json" not in content_type:
                return _failure(
                    "unknown_api_not_json",
                    content_type=content_type,
                )

        database = ready.json().get("database", {})
        print(
            json.dumps(
                {
                    "status": "ok",
                    "frontend": "vite",
                    "frontend_asset": asset_path,
                    "database": database.get("dialect"),
                    "alembic_revision": database.get("alembic_revision"),
                    "api": health.json().get("api"),
                    "readiness": ready.json().get("status"),
                },
                sort_keys=True,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

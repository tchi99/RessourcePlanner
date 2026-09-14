from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.server import ServerSettings, create_configured_app


ASSET_RE = re.compile(r"(?:src|href)=[\"'](?P<path>/assets/[^\"']+)[\"']")


def main() -> int:
    frontend_dist = ROOT / "frontend" / "dist"
    settings = ServerSettings(
        database_url="sqlite+pysqlite:///:memory:",
        frontend_dist=str(frontend_dist),
    )

    try:
        app = create_configured_app(settings)
    except Exception as exc:  # pragma: no cover - command-line diagnostic path
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "app_creation_failed",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 1

    with TestClient(app) as client:
        root = client.get("/")
        if root.status_code != 200 or "text/html" not in root.headers.get("content-type", ""):
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "frontend_index_failed",
                        "http_status": root.status_code,
                    },
                    sort_keys=True,
                )
            )
            return 1

        match = ASSET_RE.search(root.text)
        if match is None:
            print(json.dumps({"status": "failed", "reason": "frontend_asset_missing"}, sort_keys=True))
            return 1

        asset_path = match.group("path")
        asset = client.get(asset_path)
        if asset.status_code != 200:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "frontend_asset_failed",
                        "asset": asset_path,
                        "http_status": asset.status_code,
                    },
                    sort_keys=True,
                )
            )
            return 1

        health = client.get("/health")
        if health.status_code != 200:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "health_failed",
                        "http_status": health.status_code,
                    },
                    sort_keys=True,
                )
            )
            return 1

        missing_api = client.get("/api/v1/__web_runtime_smoke_missing__")
        if missing_api.status_code != 404:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "unknown_api_not_404",
                        "http_status": missing_api.status_code,
                    },
                    sort_keys=True,
                )
            )
            return 1
        content_type = missing_api.headers.get("content-type", "")
        if "application/json" not in content_type:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "unknown_api_not_json",
                        "content_type": content_type,
                    },
                    sort_keys=True,
                )
            )
            return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "frontend": "vite",
                "frontend_asset": asset_path,
                "database": health.json().get("database"),
                "api": health.json().get("api"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

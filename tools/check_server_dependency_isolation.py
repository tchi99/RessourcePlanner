from __future__ import annotations

import importlib.util
import json

from fastapi.testclient import TestClient

from app.server import create_api_app


FORBIDDEN_RUNTIME_MODULES = ("nicegui", "xlwings", "openpyxl")


def main() -> int:
    present = [name for name in FORBIDDEN_RUNTIME_MODULES if importlib.util.find_spec(name)]
    if present:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "legacy_dependencies_present",
                    "modules": present,
                },
                sort_keys=True,
            )
        )
        return 1

    app = create_api_app("sqlite+pysqlite:///:memory:")
    with TestClient(app) as client:
        response = client.get("/health")
        if response.status_code != 200:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "reason": "health_failed",
                        "http_status": response.status_code,
                    },
                    sort_keys=True,
                )
            )
            return 1
        health = response.json()

    paths = app.openapi().get("paths", {})
    required_paths = {
        "/health",
        "/api/v1/projects",
        "/api/v1/work-packages",
        "/api/v1/demands",
        "/api/v1/planning/snapshot",
    }
    missing = sorted(required_paths - set(paths))
    if missing:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "openapi_paths_missing",
                    "missing": missing,
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "database": health.get("database"),
                "api": health.get("api"),
                "openapi_paths": len(paths),
                "legacy_modules_present": [],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

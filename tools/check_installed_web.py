from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_MODULES = ("fastapi", "sqlalchemy", "alembic", "httpx", "uvicorn")
FORBIDDEN_LEGACY_MODULES = ("nicegui", "xlwings", "openpyxl")
SUPPORTED_PYTHON = {(3, 11), (3, 12)}


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    version = (sys.version_info.major, sys.version_info.minor)
    if version not in SUPPORTED_PYTHON:
        failures.append("unsupported_python")

    env_name = Path(sys.prefix).name.casefold()
    if env_name != ".venv-web":
        warnings.append("not_running_from_venv_web")

    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        failures.append("missing_server_dependencies")

    legacy = [name for name in FORBIDDEN_LEGACY_MODULES if importlib.util.find_spec(name) is not None]
    if legacy:
        failures.append("legacy_dependencies_present")

    frontend = ROOT / "frontend" / "dist"
    if not (frontend / "index.html").is_file():
        failures.append("frontend_index_missing")
    if not (frontend / "assets").is_dir():
        failures.append("frontend_assets_missing")

    payload = {
        "status": "ok" if not failures else "failed",
        "python": f"{version[0]}.{version[1]}",
        "environment": ".venv-web" if env_name == ".venv-web" else "other",
        "required_dependencies_missing": missing,
        "legacy_dependencies_present": legacy,
        "frontend_build": "ok" if not any(
            item.startswith("frontend_") for item in failures
        ) else "missing",
        "warnings": warnings,
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sys
from pathlib import Path

from .thunderbird_bridge import NATIVE_HOST_NAME, ThunderbirdSetupResult


def repair_source_host_launcher(
    setup: ThunderbirdSetupResult,
    *,
    python_executable: Path | None = None,
    source_root: Path | None = None,
) -> bool:
    """Rewrite the development-mode .bat host so cmd.exe handles Unicode paths reliably.

    Packaged releases use RessourcePlanner-ThunderbirdHost.exe and are left untouched.
    """
    manifest_path = Path(setup.integration_directory) / f"{NATIVE_HOST_NAME}.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False

    raw_host = str(payload.get("path") or "").strip().strip('"')
    if not raw_host:
        return False
    host_path = Path(raw_host)
    if host_path.suffix.casefold() not in {".bat", ".cmd"}:
        return False

    python_path = Path(python_executable or sys.executable).resolve()
    root = Path(source_root).resolve() if source_root is not None else Path(__file__).resolve().parents[1]
    tool_path = root / "tools" / "thunderbird_native_host.py"

    if not python_path.is_file():
        raise RuntimeError(f"Python utilisé par RessourcePlanner est introuvable : {python_path}")
    if not tool_path.is_file():
        raise RuntimeError(f"Le script du pont Thunderbird est introuvable : {tool_path}")

    # cmd.exe normally uses an OEM code page. Switching before the path-bearing lines
    # prevents accented/Unicode source paths from being corrupted. The explicit guards
    # also turn a vague Windows 'path not found' into a stable diagnostic code.
    content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        f'if not exist "{python_path}" (\r\n'
        "  >&2 echo RP_HOST_PYTHON_NOT_FOUND\r\n"
        "  exit /b 21\r\n"
        ")\r\n"
        f'if not exist "{tool_path}" (\r\n'
        "  >&2 echo RP_HOST_SCRIPT_NOT_FOUND\r\n"
        "  exit /b 22\r\n"
        ")\r\n"
        f'"{python_path}" -u "{tool_path}"\r\n'
        "exit /b %errorlevel%\r\n"
    )
    host_path.write_text(content, encoding="utf-8", newline="")
    return True

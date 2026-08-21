from __future__ import annotations

import os
import sys
from pathlib import Path

from .thunderbird_bridge import NATIVE_HOST_NAME, ThunderbirdSetupResult


REGISTRY_FIX_FILENAME = "RessourcePlanner-Thunderbird-Bridge-Registry.reg"


def packaged_python_environment() -> bool:
    """Detect the Microsoft Store / packaged Python environment used during development.

    Packaged desktop processes can receive virtualized HKCU/AppData views. A registry
    write that looks successful from the Python process may therefore be invisible to
    Thunderbird, which then reports `No such native application`.
    """
    executable = str(sys.executable or "").casefold()
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").casefold()
    markers = (
        "pythonsoftwarefoundation.python",
        "\\packages\\pythonsoftwarefoundation.python",
    )
    return any(marker in executable or marker in local_app_data for marker in markers)


def _reg_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def registry_fix_content(setup: ThunderbirdSetupResult) -> str:
    manifest_path = Path(setup.integration_directory) / f"{NATIVE_HOST_NAME}.json"
    escaped_manifest = _reg_escape(str(manifest_path))
    key = rf"HKEY_CURRENT_USER\Software\Mozilla\NativeMessagingHosts\{NATIVE_HOST_NAME}"
    wow_key = rf"HKEY_CURRENT_USER\Software\WOW6432Node\Mozilla\NativeMessagingHosts\{NATIVE_HOST_NAME}"
    return (
        "Windows Registry Editor Version 5.00\r\n\r\n"
        f"[{key}]\r\n"
        f'@="{escaped_manifest}"\r\n\r\n'
        f"[{wow_key}]\r\n"
        f'@="{escaped_manifest}"\r\n'
    )


def publish_registry_fix(
    setup: ThunderbirdSetupResult,
    *,
    destination_directory: Path | None = None,
) -> Path:
    destination = Path(destination_directory) if destination_directory else Path.home() / "Downloads"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / REGISTRY_FIX_FILENAME
    # UTF-16 LE with BOM is the most interoperable encoding for .reg files containing
    # arbitrary Windows paths and localized usernames.
    path.write_text(registry_fix_content(setup), encoding="utf-16")
    return path

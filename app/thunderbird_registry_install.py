from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from .thunderbird_bridge import NATIVE_HOST_NAME, ThunderbirdSetupResult


REGISTRY_FIX_FILENAME = "RessourcePlanner-Thunderbird-Bridge-Registry.reg"
EXTERNAL_BRIDGE_DIRECTORY = ".ressourceplanner/ThunderbirdBridge"


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


def _source_manifest_path(setup: ThunderbirdSetupResult) -> Path:
    return Path(setup.integration_directory) / f"{NATIVE_HOST_NAME}.json"


def _host_path_from_payload(manifest_path: Path, payload: dict[str, object]) -> Path | None:
    raw = str(payload.get("path") or "").strip().strip('"')
    if not raw:
        return None
    host_path = Path(raw)
    if not host_path.is_absolute():
        host_path = manifest_path.parent / host_path
    return host_path


def prepare_registry_visible_bundle(
    setup: ThunderbirdSetupResult,
    *,
    bundle_directory: Path | None = None,
) -> Path:
    """Stage the Mozilla manifest outside packaged/virtualized AppData.

    Microsoft Store Python can virtualize LOCALAPPDATA. Thunderbird is a separate desktop
    process and may therefore be unable to resolve a manifest stored below the packaged
    LocalCache path even when RessourcePlanner itself can launch the host successfully.

    The user's profile root is not the packaged LOCALAPPDATA location, so keep a small,
    persistent native-messaging bundle under ``~/.ressourceplanner/ThunderbirdBridge``.
    For source-mode .bat/.cmd hosts, copy the launcher there as well and point the staged
    manifest at that copy. Packaged .exe hosts remain referenced in place.
    """
    source_manifest = _source_manifest_path(setup)
    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Le manifeste Thunderbird source n'est pas un objet JSON valide.")

    destination = (
        Path(bundle_directory)
        if bundle_directory is not None
        else Path.home() / ".ressourceplanner" / "ThunderbirdBridge"
    )
    destination.mkdir(parents=True, exist_ok=True)

    source_host = _host_path_from_payload(source_manifest, payload)
    if source_host is None:
        raise RuntimeError("Le manifeste Thunderbird source ne contient aucun hôte natif.")
    if not source_host.is_file():
        raise RuntimeError(f"L'hôte Thunderbird source est introuvable : {source_host}")

    staged_host = source_host
    if source_host.suffix.casefold() in {".bat", ".cmd"}:
        staged_host = destination / source_host.name
        shutil.copy2(source_host, staged_host)

    payload["path"] = str(staged_host)
    staged_manifest = destination / f"{NATIVE_HOST_NAME}.json"
    staged_manifest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return staged_manifest


def registry_fix_content(
    setup: ThunderbirdSetupResult,
    *,
    manifest_path: Path | None = None,
) -> str:
    resolved_manifest = Path(manifest_path) if manifest_path is not None else _source_manifest_path(setup)
    escaped_manifest = _reg_escape(str(resolved_manifest))
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
    bundle_directory: Path | None = None,
) -> Path:
    staged_manifest = prepare_registry_visible_bundle(
        setup,
        bundle_directory=bundle_directory,
    )
    destination = Path(destination_directory) if destination_directory else Path.home() / "Downloads"
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / REGISTRY_FIX_FILENAME
    # UTF-16 with BOM is the most interoperable encoding for .reg files containing
    # arbitrary Windows paths and localized usernames.
    path.write_text(
        registry_fix_content(setup, manifest_path=staged_manifest),
        encoding="utf-16",
    )
    return path

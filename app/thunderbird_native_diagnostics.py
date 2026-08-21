from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .thunderbird_bridge import EXTENSION_ID, NATIVE_HOST_NAME, ThunderbirdSetupResult


@dataclass(frozen=True)
class ThunderbirdNativeDiagnostic:
    ok: bool
    manifest_ok: bool
    host_exists: bool
    host_launch_ok: bool
    registry_views: tuple[str, ...]
    detail: str


def _manifest_path(setup: ThunderbirdSetupResult) -> Path:
    return Path(setup.integration_directory) / f"{NATIVE_HOST_NAME}.json"


def _load_native_manifest(path: Path) -> tuple[dict[str, object] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "Le manifeste du pont natif est introuvable."
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Le manifeste du pont natif est illisible ({type(exc).__name__})."
    if not isinstance(payload, dict):
        return None, "Le manifeste du pont natif n'est pas un objet JSON valide."
    return payload, ""


def _host_path_from_manifest(manifest_path: Path, payload: dict[str, object]) -> Path | None:
    raw = str(payload.get("path") or "").strip().strip('"')
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path


def inspect_native_manifest(
    setup: ThunderbirdSetupResult,
) -> tuple[bool, Path | None, str]:
    manifest_path = _manifest_path(setup)
    payload, error = _load_native_manifest(manifest_path)
    if payload is None:
        return False, None, error

    if str(payload.get("name") or "") != NATIVE_HOST_NAME:
        return False, None, "Le nom du pont natif ne correspond pas au nom attendu."
    if str(payload.get("type") or "") != "stdio":
        return False, None, "Le manifeste du pont natif n'utilise pas le transport stdio attendu."

    allowed = payload.get("allowed_extensions")
    if not isinstance(allowed, list) or EXTENSION_ID not in {str(value) for value in allowed}:
        return False, None, "L'extension Thunderbird n'est pas autorisée dans le manifeste du pont natif."

    host_path = _host_path_from_manifest(manifest_path, payload)
    if host_path is None:
        return False, None, "Le manifeste ne contient pas de chemin vers l'hôte natif."
    if not host_path.is_file():
        return False, host_path, "Le programme du pont natif référencé par le manifeste est introuvable."
    return True, host_path, ""


def _register_native_manifest_windows(manifest_path: Path) -> tuple[str, ...]:
    if os.name != "nt":
        return ()

    import winreg

    key_path = rf"Software\Mozilla\NativeMessagingHosts\{NATIVE_HOST_NAME}"
    views: list[tuple[str, int]] = [("native", 0)]
    for label, attribute in (("64-bit", "KEY_WOW64_64KEY"), ("32-bit", "KEY_WOW64_32KEY")):
        flag = int(getattr(winreg, attribute, 0) or 0)
        if flag and all(existing_flag != flag for _existing_label, existing_flag in views):
            views.append((label, flag))

    registered: list[str] = []
    errors: list[OSError] = []
    for label, view_flag in views:
        try:
            access = int(getattr(winreg, "KEY_SET_VALUE", 0x0002)) | view_flag
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, access) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))
            registered.append(label)
        except OSError as exc:
            errors.append(exc)

    if not registered and errors:
        raise errors[-1]
    return tuple(registered)


def probe_native_host_launch(
    host_path: Path,
    *,
    runner: Callable[..., object] | None = None,
) -> tuple[bool, str]:
    """Launch the host with EOF only, so the probe cannot create a fake heartbeat."""
    run = runner or subprocess.run
    kwargs = {
        "input": b"",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": 6,
        "check": False,
    }
    creation_flag = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    if creation_flag:
        kwargs["creationflags"] = creation_flag
    try:
        completed = run([str(host_path)], **kwargs)
    except subprocess.TimeoutExpired:
        return False, "Le programme du pont natif ne termine pas son auto-test."
    except OSError as exc:
        return False, f"Windows n'arrive pas à démarrer le pont natif ({type(exc).__name__}: {exc})."

    code = int(getattr(completed, "returncode", 1))
    if code == 0:
        return True, ""
    stderr = getattr(completed, "stderr", b"") or b""
    if isinstance(stderr, bytes):
        detail = stderr.decode("utf-8", errors="replace").strip()
    else:
        detail = str(stderr).strip()
    if detail:
        detail = " ".join(detail.split())[:240]
        return False, f"Le pont natif quitte avec le code {code}: {detail}"
    return False, f"Le pont natif quitte avec le code {code}."


def repair_and_diagnose_native_host(
    setup: ThunderbirdSetupResult,
    *,
    runner: Callable[..., object] | None = None,
) -> ThunderbirdNativeDiagnostic:
    manifest_path = _manifest_path(setup)
    try:
        registry_views = _register_native_manifest_windows(manifest_path)
    except OSError as exc:
        return ThunderbirdNativeDiagnostic(
            ok=False,
            manifest_ok=False,
            host_exists=False,
            host_launch_ok=False,
            registry_views=(),
            detail=f"Impossible d'enregistrer le pont natif dans Windows ({type(exc).__name__}: {exc}).",
        )

    manifest_ok, host_path, detail = inspect_native_manifest(setup)
    if not manifest_ok:
        return ThunderbirdNativeDiagnostic(
            ok=False,
            manifest_ok=False,
            host_exists=bool(host_path and host_path.is_file()),
            host_launch_ok=False,
            registry_views=registry_views,
            detail=detail,
        )

    assert host_path is not None
    launch_ok, launch_detail = probe_native_host_launch(host_path, runner=runner)
    return ThunderbirdNativeDiagnostic(
        ok=launch_ok,
        manifest_ok=True,
        host_exists=True,
        host_launch_ok=launch_ok,
        registry_views=registry_views,
        detail=launch_detail or "Le manifeste, l'enregistrement Windows et le programme du pont natif sont valides.",
    )

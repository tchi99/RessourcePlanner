from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Sequence


NATIVE_HOST_NAME = "com.ressourceplanner.bridge"
EXTENSION_ID = "ressourceplanner-drafts" + chr(64) + "local"
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 20


@dataclass(frozen=True)
class ThunderbirdDraftRequest:
    message_id: str
    batch_id: str
    to_address: str
    subject: str
    body: str


@dataclass(frozen=True)
class ThunderbirdBatchStatus:
    total: int = 0
    created: int = 0
    pending: int = 0
    failed: int = 0
    extension_seen_recently: bool = False


@dataclass(frozen=True)
class ThunderbirdSetupResult:
    extension_package: Path
    integration_directory: Path
    native_host_registered: bool


def _bridge_directory() -> Path:
    local = str(os.environ.get("LOCALAPPDATA") or "").strip()
    root = Path(local) if local else Path.home() / ".ressourceplanner"
    path = root / "RessourcePlanner" / "ThunderbirdBridge" if local else root / "ThunderbirdBridge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _queue_path() -> Path:
    return _bridge_directory() / "queue.json"


def _default_state() -> dict[str, Any]:
    return {"version": 1, "last_seen": 0.0, "messages": {}}


def _load_state() -> dict[str, Any]:
    path = _queue_path()
    if not path.exists():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(data, dict):
        return _default_state()
    data.setdefault("version", 1)
    data.setdefault("last_seen", 0.0)
    if not isinstance(data.get("messages"), dict):
        data["messages"] = {}
    return data


def _save_state(data: dict[str, Any]) -> None:
    path = _queue_path()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def queue_thunderbird_drafts(requests: Sequence[ThunderbirdDraftRequest]) -> int:
    rows = tuple(requests)
    if not rows:
        return 0
    data = _load_state()
    messages = data.setdefault("messages", {})
    queued = 0
    for row in rows:
        message_id = str(row.message_id or "").strip()
        batch_id = str(row.batch_id or "").strip()
        recipient = str(row.to_address or "").strip()
        if not message_id or not batch_id or not recipient:
            raise ValueError("Chaque brouillon Thunderbird doit avoir un identifiant, un lot et un destinataire.")
        existing = messages.get(message_id)
        if isinstance(existing, dict) and str(existing.get("status") or "") == "created":
            continue
        messages[message_id] = {
            "message_id": message_id,
            "batch_id": batch_id,
            "to_address": recipient,
            "subject": str(row.subject or ""),
            "body": str(row.body or ""),
            "status": "pending",
            "lease_until": 0.0,
            "error": "",
        }
        queued += 1
    _save_state(data)
    return queued


def thunderbird_batch_status(batch_id: str) -> ThunderbirdBatchStatus:
    data = _load_state()
    rows = [
        row
        for row in data.get("messages", {}).values()
        if isinstance(row, dict) and str(row.get("batch_id") or "") == str(batch_id)
    ]
    statuses = [str(row.get("status") or "pending") for row in rows]
    now = time.time()
    try:
        last_seen = float(data.get("last_seen") or 0.0)
    except (TypeError, ValueError):
        last_seen = 0.0
    return ThunderbirdBatchStatus(
        total=len(rows),
        created=sum(value == "created" for value in statuses),
        pending=sum(value in {"pending", "leased"} for value in statuses),
        failed=sum(value == "failed" for value in statuses),
        extension_seen_recently=bool(last_seen and now - last_seen <= HEARTBEAT_SECONDS),
    )


def thunderbird_created_message_ids(batch_id: str) -> tuple[str, ...]:
    data = _load_state()
    return tuple(
        str(message_id)
        for message_id, row in data.get("messages", {}).items()
        if isinstance(row, dict)
        and str(row.get("batch_id") or "") == str(batch_id)
        and str(row.get("status") or "") == "created"
    )


def discard_thunderbird_batch(batch_id: str) -> None:
    data = _load_state()
    messages = data.get("messages", {})
    if not isinstance(messages, dict):
        return
    kept = {
        key: value
        for key, value in messages.items()
        if not isinstance(value, dict) or str(value.get("batch_id") or "") != str(batch_id)
    }
    if len(kept) != len(messages):
        data["messages"] = kept
        _save_state(data)


def _sanitize_bridge_error(value: Any) -> str:
    text = " ".join(str(value or "ThunderbirdError").split())
    return text[:160]


def handle_native_message(message: dict[str, Any]) -> dict[str, Any]:
    action = str(message.get("action") or "").strip().lower()
    data = _load_state()
    data["last_seen"] = time.time()

    if action in {"heartbeat", "status"}:
        _save_state(data)
        return {"ok": True}

    if action == "poll":
        now = time.time()
        selected: list[dict[str, str]] = []
        messages = data.get("messages", {})
        if isinstance(messages, dict):
            for row in messages.values():
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or "pending")
                try:
                    lease_until = float(row.get("lease_until") or 0.0)
                except (TypeError, ValueError):
                    lease_until = 0.0
                if status == "created":
                    continue
                if status == "leased" and lease_until > now:
                    continue
                if status not in {"pending", "failed", "leased"}:
                    continue
                row["status"] = "leased"
                row["lease_until"] = now + LEASE_SECONDS
                row["error"] = ""
                selected.append(
                    {
                        "message_id": str(row.get("message_id") or ""),
                        "batch_id": str(row.get("batch_id") or ""),
                        "to_address": str(row.get("to_address") or ""),
                        "subject": str(row.get("subject") or ""),
                        "body": str(row.get("body") or ""),
                    }
                )
                if len(selected) >= 20:
                    break
        _save_state(data)
        return {"ok": True, "messages": selected}

    if action == "ack":
        messages = data.get("messages", {})
        results = message.get("results") or []
        if isinstance(messages, dict) and isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    continue
                message_id = str(result.get("message_id") or "").strip()
                row = messages.get(message_id)
                if not message_id or not isinstance(row, dict):
                    continue
                if bool(result.get("ok")):
                    row["status"] = "created"
                    row["lease_until"] = 0.0
                    row["error"] = ""
                else:
                    row["status"] = "failed"
                    row["lease_until"] = 0.0
                    row["error"] = _sanitize_bridge_error(result.get("error"))
        _save_state(data)
        return {"ok": True}

    _save_state(data)
    return {"ok": False, "error": "unsupported_action"}


def _read_native_message(stream: BinaryIO) -> dict[str, Any] | None:
    raw_length = stream.read(4)
    if not raw_length:
        return None
    if len(raw_length) != 4:
        raise EOFError("Native messaging header incomplet.")
    length = struct.unpack("<I", raw_length)[0]
    if length <= 0 or length > 16 * 1024 * 1024:
        raise ValueError("Taille de message native invalide.")
    payload = stream.read(length)
    if len(payload) != length:
        raise EOFError("Native messaging payload incomplet.")
    decoded = json.loads(payload.decode("utf-8"))
    return decoded if isinstance(decoded, dict) else {}


def _write_native_message(stream: BinaryIO, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("<I", len(encoded)))
    stream.write(encoded)
    stream.flush()


def run_native_host(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    source = stdin or sys.stdin.buffer
    target = stdout or sys.stdout.buffer
    try:
        message = _read_native_message(source)
        if message is None:
            return 0
        _write_native_message(target, handle_native_message(message))
        return 0
    except Exception:
        try:
            _write_native_message(target, {"ok": False, "error": "native_host_error"})
        except Exception:
            pass
        return 1


_EXTENSION_MANIFEST = {
    "manifest_version": 2,
    "name": "RessourcePlanner Draft Bridge",
    "version": "1.0.0",
    "description": "Crée uniquement des brouillons Thunderbird approuvés par RessourcePlanner.",
    "permissions": ["compose", "compose.save", "nativeMessaging"],
    "background": {"scripts": ["background.js"]},
    "browser_specific_settings": {
        "gecko": {"id": EXTENSION_ID, "strict_min_version": "102.0"}
    },
}

_EXTENSION_BACKGROUND = r'''const HOST = "com.ressourceplanner.bridge";
let busy = false;

async function processPending() {
  if (busy) return;
  busy = true;
  try {
    const response = await browser.runtime.sendNativeMessage(HOST, {action: "poll"});
    const pending = response && Array.isArray(response.messages) ? response.messages : [];
    const results = [];
    for (const item of pending) {
      let tab = null;
      try {
        tab = await browser.compose.beginNew({
          to: [String(item.to_address || "")],
          subject: String(item.subject || ""),
          plainTextBody: String(item.body || ""),
          isPlainText: true,
          customHeaders: [{
            name: "X-RessourcePlanner-Message-ID",
            value: String(item.message_id || "")
          }]
        });
        await browser.compose.saveMessage(tab.id, {mode: "draft"});
        try { await browser.tabs.remove(tab.id); } catch (_) {}
        results.push({message_id: String(item.message_id || ""), ok: true});
      } catch (error) {
        if (tab && tab.id) {
          try { await browser.tabs.remove(tab.id); } catch (_) {}
        }
        results.push({
          message_id: String(item.message_id || ""),
          ok: false,
          error: error && error.name ? String(error.name) : "ThunderbirdError"
        });
      }
    }
    if (results.length) {
      await browser.runtime.sendNativeMessage(HOST, {action: "ack", results});
    }
  } catch (_) {
    // The host is optional until RessourcePlanner configures it. Stay silent and retry.
  } finally {
    busy = false;
  }
}

processPending();
setInterval(processPending, 4000);
'''


def _write_extension_package(destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(_EXTENSION_MANIFEST, ensure_ascii=False, indent=2))
        archive.writestr("background.js", _EXTENSION_BACKGROUND)


def prepare_thunderbird_integration() -> ThunderbirdSetupResult:
    if os.name != "nt":
        raise RuntimeError("La configuration Thunderbird est disponible uniquement sous Windows pour l'instant.")

    root = _bridge_directory()
    source_root = Path(__file__).resolve().parents[1]
    if bool(getattr(sys, "frozen", False)):
        host_path = Path(sys.executable).resolve().parent / "RessourcePlanner-ThunderbirdHost.exe"
        if not host_path.exists():
            raise RuntimeError(
                "Le composant Thunderbird n'est pas présent à côté de l'application installée."
            )
    else:
        tool = source_root / "tools" / "thunderbird_native_host.py"
        if not tool.exists():
            raise RuntimeError("Le composant natif Thunderbird est introuvable dans le projet.")
        host_path = root / "thunderbird_native_host.bat"
        host_path.write_text(
            "@echo off\r\n"
            f'"{sys.executable}" -u "{tool}"\r\n',
            encoding="utf-8",
        )

    manifest_path = root / f"{NATIVE_HOST_NAME}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": NATIVE_HOST_NAME,
                "description": "RessourcePlanner Thunderbird draft bridge",
                "path": str(host_path),
                "type": "stdio",
                "allowed_extensions": [EXTENSION_ID],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    import winreg

    key_path = rf"Software\Mozilla\NativeMessagingHosts\{NATIVE_HOST_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))

    extension_path = root / "RessourcePlanner-Thunderbird-Draft-Bridge.xpi"
    _write_extension_package(extension_path)
    return ThunderbirdSetupResult(
        extension_package=extension_path,
        integration_directory=root,
        native_host_registered=True,
    )


def open_thunderbird_integration_folder() -> Path:
    path = _bridge_directory()
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", str(path)])
    return path

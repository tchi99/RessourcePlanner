from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .domain.cutover_policy import normalize_planning_engine_mode


def _runtime_base_dir() -> Path:
    """Directory used for local per-installation files.

    In normal Python development this is the repository root. In a PyInstaller/
    nicegui-pack executable, ``sys.executable`` points to the distributed .exe,
    so configuration and user preferences live beside that executable rather than
    inside PyInstaller's temporary extraction directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


BASE_DIR = _runtime_base_dir()
CONFIG_PATH = BASE_DIR / "app_config.json"


@dataclass(slots=True)
class AppConfig:
    workbook: Path | None
    refresh_seconds: float = 3.0
    save_on_write: bool = True
    host: str = "127.0.0.1"
    port: int = 8080
    planning_engine_mode: str = "legacy"


def _resolve_workbook(value: str | None) -> Path | None:
    if not value or not str(value).strip():
        return None
    workbook = Path(str(value).strip().strip('"'))
    if not workbook.is_absolute():
        workbook = (BASE_DIR / workbook).resolve()
    return workbook


def load_config() -> AppConfig:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    return AppConfig(
        workbook=_resolve_workbook(raw.get("workbook")),
        refresh_seconds=float(raw.get("refresh_seconds", 3.0)),
        save_on_write=bool(raw.get("save_on_write", True)),
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 8080)),
        planning_engine_mode=normalize_planning_engine_mode(raw.get("planning_engine_mode")),
    )


def save_workbook_path(path: str | Path | None) -> None:
    raw = {}
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    raw.setdefault("refresh_seconds", 3)
    raw.setdefault("save_on_write", True)
    raw.setdefault("host", "127.0.0.1")
    raw.setdefault("port", 8080)
    raw.setdefault("planning_engine_mode", "legacy")
    raw["workbook"] = "" if path is None else str(Path(path))
    CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

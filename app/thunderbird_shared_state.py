from __future__ import annotations

import os
from pathlib import Path


BRIDGE_DIRECTORY_ENV = "RESSOURCEPLANNER_THUNDERBIRD_BRIDGE_DIR"


def shared_bridge_directory() -> Path:
    """Return one bridge directory visible to both RessourcePlanner and Thunderbird.

    Do not base the runtime queue/heartbeat path on LOCALAPPDATA. Microsoft Store Python
    can expose a packaged LocalCache value there while Thunderbird inherits the normal
    desktop LOCALAPPDATA value. The two processes would then communicate successfully
    through nativeMessaging but read/write different queue.json files.
    """
    override = str(os.environ.get(BRIDGE_DIRECTORY_ENV) or "").strip()
    if override:
        path = Path(override)
    else:
        profile = str(os.environ.get("USERPROFILE") or "").strip()
        root = Path(profile) if profile else Path.home()
        path = root / ".ressourceplanner" / "ThunderbirdBridge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def install_shared_bridge_directory() -> Path:
    """Make the legacy bridge module use the cross-process stable directory."""
    from . import thunderbird_bridge

    thunderbird_bridge._bridge_directory = shared_bridge_directory
    return shared_bridge_directory()

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


EXTENSION_FILENAME = "RessourcePlanner-Thunderbird-Draft-Bridge.xpi"


def preferred_visible_install_directory(home: Path | None = None) -> Path | None:
    """Return a user-visible folder for the one-time Thunderbird XPI install copy."""
    root = Path(home) if home is not None else Path.home()
    for name in ("Downloads", "Documents"):
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return None


def publish_thunderbird_extension(
    source: Path,
    *,
    home: Path | None = None,
) -> Path:
    """Copy the generated XPI to a visible folder when possible."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError("Le fichier d'extension Thunderbird n'a pas été créé.")

    destination_directory = preferred_visible_install_directory(home)
    if destination_directory is None:
        return source

    destination = destination_directory / EXTENSION_FILENAME
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return destination


def reveal_thunderbird_extension(
    extension_path: Path,
    *,
    platform_name: str | None = None,
    launcher: Callable[..., object] | None = None,
) -> Path:
    """Open Explorer with the exact XPI selected instead of opening an arbitrary folder."""
    path = Path(extension_path)
    if not path.is_file():
        raise FileNotFoundError("Le fichier d'extension Thunderbird est introuvable.")

    effective_platform = platform_name or os.name
    if effective_platform == "nt":
        run = launcher or subprocess.Popen
        run(["explorer.exe", "/select,", str(path)])
    return path


def visible_folder_label(path: Path) -> str:
    name = Path(path).parent.name.casefold()
    if name == "downloads":
        return "Téléchargements"
    if name == "documents":
        return "Documents"
    return "le dossier d'installation RessourcePlanner"

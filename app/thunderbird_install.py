from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


EXTENSION_FILENAME = "RessourcePlanner-Thunderbird-Draft-Bridge.xpi"


def _clean_path(value: Path | str) -> Path:
    """Normalize a path coming from UI/runtime text before touching Windows APIs.

    Windows rejects file names ending with spaces or control characters.  The XPI
    path is normally generated internally, but this defensive normalization also
    protects reveal/publish calls from accidental whitespace or copied quoted paths.
    """
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return Path(text)


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
    source = _clean_path(source)
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
    path = _clean_path(extension_path)
    if not path.is_file():
        raise FileNotFoundError("Le fichier d'extension Thunderbird est introuvable.")

    effective_platform = platform_name or os.name
    if effective_platform == "nt":
        run = launcher or subprocess.Popen
        # Explorer expects /select,<file> as one command argument. Passing '/select,'
        # and the file as two arguments can be rejected by some Windows builds with
        # OSError/Errno 22 (invalid argument).
        run(["explorer.exe", f"/select,{path}"])
    return path


def visible_folder_label(path: Path) -> str:
    name = _clean_path(path).parent.name.casefold()
    if name == "downloads":
        return "Téléchargements"
    if name == "documents":
        return "Documents"
    return "le dossier d'installation RessourcePlanner"

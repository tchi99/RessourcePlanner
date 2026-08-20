from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from nicegui import ui

from . import communication_mail_clients_ui
from .thunderbird_bridge import prepare_thunderbird_integration


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
    """Copy the generated XPI to a visible folder when possible.

    The native messaging files remain in RessourcePlanner's local integration directory;
    only the extension package is copied for easier manual selection in Thunderbird.
    """
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


def _visible_folder_label(path: Path) -> str:
    name = path.parent.name.casefold()
    if name == "downloads":
        return "Téléchargements"
    if name == "documents":
        return "Documents"
    return "le dossier d'installation RessourcePlanner"


def _thunderbird_setup_dialog(self) -> None:
    try:
        setup = prepare_thunderbird_integration()
        install_path = publish_thunderbird_extension(setup.extension_package)
        reveal_thunderbird_extension(install_path)
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)
        return

    folder_label = _visible_folder_label(install_path)

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-[95vw]"):
        ui.label("Configurer Thunderbird").classes("text-xl font-bold")
        ui.label(
            "Le pont natif RessourcePlanner est enregistré pour ton compte Windows et une copie du fichier XPI a été préparée pour l'installation manuelle."
        ).classes("text-sm")

        with ui.card().classes("w-full border border-blue-200 bg-blue-50"):
            ui.label("Installation unique dans Thunderbird").classes("font-semibold text-blue-900")
            ui.label(
                f"Le fichier {EXTENSION_FILENAME} a été placé dans {folder_label} et Explorer l'a sélectionné. "
                "Dans Thunderbird : Modules complémentaires et thèmes → bouton engrenage → Installer un module depuis un fichier. "
                f"Dans la fenêtre de sélection, ouvre {folder_label}, choisis ce fichier, puis redémarre Thunderbird."
            ).classes("text-sm text-blue-900")

        ui.label(
            "Le sélecteur de fichiers de Thunderbird peut s'ouvrir dans Documents même si Explorer affiche un autre dossier. "
            "C'est normal : navigue simplement vers le dossier indiqué ci-dessus."
        ).classes("text-xs muted")

        ui.label(
            "L'extension demande seulement les permissions nécessaires pour créer et enregistrer des brouillons et communiquer avec le pont local. "
            "Elle ne possède aucune permission d'envoi automatique."
        ).classes("text-xs muted")

        with ui.row().classes("w-full justify-between items-center"):
            ui.button(
                "Afficher le fichier XPI",
                icon="folder_open",
                on_click=lambda: reveal_thunderbird_extension(install_path),
            ).props("outline no-caps")
            ui.button("Fermer", on_click=dialog.close).props("unelevated no-caps color=primary")
    dialog.open()


def install_thunderbird_setup_fix() -> None:
    """Improve the one-time Thunderbird XPI installation UX without changing transport rules."""
    if getattr(communication_mail_clients_ui, "_thunderbird_setup_fix_installed", False):
        return
    communication_mail_clients_ui._thunderbird_setup_dialog = _thunderbird_setup_dialog
    communication_mail_clients_ui._thunderbird_setup_fix_installed = True

from __future__ import annotations

import os

from nicegui import ui

from . import communication_mail_clients_ui
from .thunderbird_bridge import prepare_thunderbird_integration
from .thunderbird_extension_diagnostics import (
    DIAGNOSTIC_EXTENSION_VERSION,
    enhance_thunderbird_extension,
)
from .thunderbird_install import (
    EXTENSION_FILENAME,
    publish_thunderbird_extension,
    reveal_thunderbird_extension,
    visible_folder_label,
)
from .thunderbird_native_diagnostics import repair_and_diagnose_native_host
from .thunderbird_registry_install import packaged_python_environment, publish_registry_fix
from .thunderbird_source_host import repair_source_host_launcher


def _try_reveal_extension(path) -> bool:
    """Reveal the XPI when possible without making Explorer a setup dependency."""
    try:
        reveal_thunderbird_extension(path)
        return True
    except (OSError, ValueError):
        return False


def _thunderbird_setup_dialog(self) -> None:
    try:
        setup = prepare_thunderbird_integration()
        enhance_thunderbird_extension(setup.extension_package)
        install_path = publish_thunderbird_extension(setup.extension_package)
        repair_source_host_launcher(setup)
        diagnostic = repair_and_diagnose_native_host(setup)
        if not diagnostic.ok:
            _try_reveal_extension(install_path)
            folder_label = visible_folder_label(install_path)
            ui.notify(
                "Le XPI a bien été préparé dans "
                f"{folder_label}, mais le pont natif Windows ne passe pas son auto-test : "
                f"{diagnostic.detail}",
                type="negative",
                timeout=14000,
            )
            return
        registry_fix_path = publish_registry_fix(setup) if packaged_python_environment() else None
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)
        return

    revealed = _try_reveal_extension(install_path)
    folder_label = visible_folder_label(install_path)

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-[95vw]"):
        ui.label("Configurer Thunderbird").classes("text-xl font-bold")
        ui.label(
            "Le programme local RessourcePlanner est prêt et une copie du fichier XPI a été préparée pour l'installation manuelle."
        ).classes("text-sm")

        with ui.card().classes("w-full border border-green-200 bg-green-50"):
            ui.label("Hôte natif local validé").classes("font-semibold text-green-900")
            registry_label = ", ".join(diagnostic.registry_views) or "registre utilisateur"
            ui.label(
                f"Le manifeste, le programme du pont et son démarrage local ont été validés. Écriture registre demandée : {registry_label}."
            ).classes("text-sm text-green-900")

        if registry_fix_path is not None:
            with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
                ui.label("Python Microsoft Store détecté — une étape registre est requise").classes(
                    "font-semibold text-amber-900"
                )
                ui.label(
                    "Cette version de Python s'exécute dans un package Windows. Ses écritures HKCU peuvent être virtualisées : "
                    "RessourcePlanner les voit, mais Thunderbird peut répondre « No such native application ». "
                    "Un fichier .reg a donc été préparé dans Téléchargements pour écrire la clé dans le registre Windows réellement visible par Thunderbird."
                ).classes("text-sm text-amber-900")

                def install_registry_fix() -> None:
                    try:
                        os.startfile(str(registry_fix_path))
                        ui.notify(
                            "Accepte l'importation dans l'Éditeur du Registre, puis ferme complètement et redémarre Thunderbird.",
                            type="info",
                            timeout=9000,
                        )
                    except OSError as exc:
                        ui.notify(
                            f"Impossible d'ouvrir le correctif registre ({type(exc).__name__}). Le fichier est dans Téléchargements.",
                            type="negative",
                            timeout=9000,
                        )

                ui.button(
                    "Installer la clé registre Thunderbird",
                    icon="settings",
                    on_click=install_registry_fix,
                ).props("unelevated no-caps color=warning")

        with ui.card().classes("w-full border border-blue-200 bg-blue-50"):
            ui.label("Installer / mettre à jour l'extension Thunderbird").classes("font-semibold text-blue-900")
            explorer_text = (
                "Explorer l'a sélectionné. "
                if revealed
                else "Explorer n'a pas pu le sélectionner automatiquement, mais le fichier a bien été créé. "
            )
            ui.label(
                f"Le fichier {EXTENSION_FILENAME} version {DIAGNOSTIC_EXTENSION_VERSION} a été placé dans {folder_label}. {explorer_text}"
                "Dans Thunderbird : Modules complémentaires et thèmes → bouton engrenage → Installer un module depuis un fichier. "
                f"Dans la fenêtre de sélection, ouvre {folder_label}, choisis ce fichier, puis redémarre Thunderbird."
            ).classes("text-sm text-blue-900")

        with ui.card().classes("w-full border border-amber-300 bg-amber-50"):
            ui.label("Diagnostic côté Thunderbird").classes("font-semibold text-amber-900")
            ui.label(
                "Cette version ajoute un bouton « RessourcePlanner Bridge » dans Thunderbird. Après l'installation, ouvre ce bouton : "
                "il indiquera directement si l'extension est chargée et affichera l'erreur exacte retournée par nativeMessaging. "
                "Le test n'envoie aucun courriel."
            ).classes("text-sm text-amber-900")

        ui.label(
            "Comme la version du XPI a été augmentée, installe ce nouveau fichier même si RessourcePlanner Draft Bridge est déjà présent. Thunderbird doit remplacer l'ancienne version."
        ).classes("text-xs muted")

        ui.label(
            "L'extension demande seulement les permissions nécessaires pour créer et enregistrer des brouillons, stocker son diagnostic local et communiquer avec le pont. "
            "Elle ne possède aucune permission d'envoi automatique."
        ).classes("text-xs muted")

        def reveal_again() -> None:
            if not _try_reveal_extension(install_path):
                ui.notify(
                    f"Le fichier XPI est disponible dans {folder_label}; ouvre ce dossier manuellement.",
                    type="warning",
                    timeout=7000,
                )

        with ui.row().classes("w-full justify-between items-center"):
            ui.button(
                "Afficher le fichier XPI",
                icon="folder_open",
                on_click=reveal_again,
            ).props("outline no-caps")
            ui.button("Fermer", on_click=dialog.close).props("unelevated no-caps color=primary")
    dialog.open()


def install_thunderbird_setup_fix() -> None:
    """Improve the one-time Thunderbird XPI installation UX without changing transport rules."""
    if getattr(communication_mail_clients_ui, "_thunderbird_setup_fix_installed", False):
        return
    communication_mail_clients_ui._thunderbird_setup_dialog = _thunderbird_setup_dialog
    communication_mail_clients_ui._thunderbird_setup_fix_installed = True

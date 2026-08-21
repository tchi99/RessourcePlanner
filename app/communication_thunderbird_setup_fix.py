from __future__ import annotations

from nicegui import ui

from . import communication_mail_clients_ui
from .thunderbird_bridge import prepare_thunderbird_integration
from .thunderbird_install import (
    EXTENSION_FILENAME,
    publish_thunderbird_extension,
    reveal_thunderbird_extension,
    visible_folder_label,
)
from .thunderbird_native_diagnostics import repair_and_diagnose_native_host
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
    except Exception as exc:
        ui.notify(str(exc), type="negative", timeout=9000)
        return

    revealed = _try_reveal_extension(install_path)
    folder_label = visible_folder_label(install_path)

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-[95vw]"):
        ui.label("Configurer Thunderbird").classes("text-xl font-bold")
        ui.label(
            "Le pont natif RessourcePlanner est enregistré pour ton compte Windows et une copie du fichier XPI a été préparée pour l'installation manuelle."
        ).classes("text-sm")

        with ui.card().classes("w-full border border-green-200 bg-green-50"):
            ui.label("Pont natif Windows validé").classes("font-semibold text-green-900")
            registry_label = ", ".join(diagnostic.registry_views) or "registre utilisateur"
            ui.label(
                f"Le manifeste, le programme du pont et son démarrage local ont été validés. Enregistrement : {registry_label}."
            ).classes("text-sm text-green-900")

        with ui.card().classes("w-full border border-blue-200 bg-blue-50"):
            ui.label("Installation unique dans Thunderbird").classes("font-semibold text-blue-900")
            explorer_text = (
                "Explorer l'a sélectionné. "
                if revealed
                else "Explorer n'a pas pu le sélectionner automatiquement, mais le fichier a bien été créé. "
            )
            ui.label(
                f"Le fichier {EXTENSION_FILENAME} a été placé dans {folder_label}. {explorer_text}"
                "Dans Thunderbird : Modules complémentaires et thèmes → bouton engrenage → Installer un module depuis un fichier. "
                f"Dans la fenêtre de sélection, ouvre {folder_label}, choisis ce fichier, puis redémarre Thunderbird."
            ).classes("text-sm text-blue-900")

        ui.label(
            "Si l'extension RessourcePlanner Draft Bridge est déjà installée et activée, il n'est pas nécessaire de la réinstaller uniquement pour réparer l'enregistrement du pont : redémarre Thunderbird après cette configuration."
        ).classes("text-xs muted")

        ui.label(
            "Le sélecteur de fichiers de Thunderbird peut s'ouvrir dans Documents même si Explorer affiche un autre dossier. "
            "C'est normal : navigue simplement vers le dossier indiqué ci-dessus."
        ).classes("text-xs muted")

        ui.label(
            "L'extension demande seulement les permissions nécessaires pour créer et enregistrer des brouillons et communiquer avec le pont local. "
            "Elle ne possède aucune permission d'envoi automatique."
        ).classes("text-xs muted")

        ui.label(
            "Si RessourcePlanner indique encore « Pont Thunderbird non détecté récemment » après le redémarrage, le programme natif est alors validé et le problème se situe probablement côté extension Thunderbird (extension désactivée/non chargée ou accès nativeMessaging)."
        ).classes("text-xs text-amber-800")

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

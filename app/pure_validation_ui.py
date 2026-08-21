from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from . import planning_cutover, ui as ui_module, v15_refinements
from .pure_validation import load_validation_state, record_pure_cycle


PublishFn = Callable[[Any, Any], dict[str, Any]]


def _render_validation_card(self: ui_module.PlannerUI) -> None:
    validation = load_validation_state()
    installed = bool(getattr(v15_refinements, "_pure_engine_direct_installed", False))

    with ui.card().classes("section-card w-full max-w-4xl"):
        ui.label("Moteur de planification — V1.8B").classes("text-lg font-semibold")
        if installed:
            ui.label("✓ Moteur actif : pure — moteur autoritaire unique").classes(
                "text-sm text-green-700 font-medium"
            )
        else:
            ui.label("Moteur pur non installé dans le runtime courant.").classes(
                "text-sm text-red-700 font-medium"
            )

        ui.label(
            "La période de validation terrain est terminée. Les anciens modes de rollback "
            "ne font plus partie du runtime de production."
        ).classes("text-sm muted")

        successes = int(validation.get("pure_success_count") or 0)
        errors = int(validation.get("pure_error_count") or 0)
        consecutive = int(validation.get("consecutive_pure_successes") or 0)
        last_success = str(validation.get("last_pure_success_at") or "Jamais")
        last_error = str(validation.get("last_pure_error_at") or "Jamais")
        duration = float(validation.get("last_total_seconds") or 0.0)

        ui.separator()
        ui.label("Journal technique local du moteur pur").classes("font-medium")
        with ui.row().classes("w-full gap-6 flex-wrap"):
            ui.label(f"Cycles réussis : {successes}").classes("text-sm")
            ui.label(f"Succès consécutifs : {consecutive}").classes("text-sm")
            ui.label(f"Erreurs : {errors}").classes("text-sm")
        ui.label(
            f"Dernier succès : {last_success} · dernière durée : {duration:.3f} s"
        ).classes("text-xs muted")
        if errors:
            error_type = str(validation.get("last_error_type") or "Erreur inconnue")
            ui.label(f"Dernière erreur : {last_error} · {error_type}").classes(
                "text-xs text-red-700"
            )
        ui.label(
            "Ce journal contient seulement des compteurs et métriques techniques locales; "
            "aucun projet, technicien, demande, localisation ou contenu du classeur."
        ).classes("text-xs muted")


def install_pure_validation_ui() -> None:
    """Expose the authoritative pure-engine status and technical local evidence."""
    if getattr(ui_module.PlannerUI, "_pure_validation_ui_installed", False):
        return

    original_render_settings = ui_module.PlannerUI.render_settings
    original_publish: PublishFn = planning_cutover._publish_planning_performance

    def render_settings_with_validation(self: ui_module.PlannerUI) -> None:
        original_render_settings(self)
        _render_validation_card(self)

    def publish_with_validation(repository: Any, sample: Any) -> dict[str, Any]:
        data = original_publish(repository, sample)
        record_pure_cycle(data)
        return data

    ui_module.PlannerUI.render_settings = render_settings_with_validation
    planning_cutover._publish_planning_performance = publish_with_validation
    ui_module.PlannerUI._pure_validation_ui_installed = True

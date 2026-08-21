from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from . import planning_cutover, ui as ui_module, v15_refinements
from .config import load_config, save_planning_engine_mode
from .domain.cutover_policy import GUARDED_PURE_MODE, LEGACY_MODE, PURE_MODE
from .pure_validation import load_validation_state, record_pure_cycle


PublishFn = Callable[[Any, Any], dict[str, Any]]


def _active_runtime_mode() -> str:
    if getattr(v15_refinements, "_pure_engine_direct_installed", False):
        return PURE_MODE
    if getattr(v15_refinements, "_guarded_pure_cutover_installed", False):
        return GUARDED_PURE_MODE
    return LEGACY_MODE


def _mode_label(mode: str) -> str:
    return {
        PURE_MODE: "pure — moteur pur direct",
        GUARDED_PURE_MODE: "guarded_pure — comparaison avec legacy",
        LEGACY_MODE: "legacy — moteur historique",
    }.get(mode, mode)


def _render_validation_card(self: ui_module.PlannerUI) -> None:
    configured = load_config().planning_engine_mode
    active = _active_runtime_mode()
    validation = load_validation_state()

    with ui.card().classes("section-card w-full max-w-4xl"):
        ui.label("Moteur de planification — validation V1.8B").classes(
            "text-lg font-semibold"
        )
        ui.label(
            "La bascule vers le moteur pur reste explicite sur les installations existantes. "
            "Changer ce réglage prend effet au prochain redémarrage de RessourcePlanner."
        ).classes("text-sm muted")

        with ui.row().classes("w-full gap-6 flex-wrap"):
            ui.label(f"Mode actif : {_mode_label(active)}").classes("text-sm font-medium")
            ui.label(f"Mode configuré : {_mode_label(configured)}").classes("text-sm")

        if configured != active:
            ui.label(
                "Un changement de moteur est enregistré. Redémarre l'application pour l'appliquer."
            ).classes("text-sm text-amber-700")

        def choose_mode(mode: str) -> None:
            saved = save_planning_engine_mode(mode)
            ui.notify(
                f"Mode {saved} enregistré. Redémarre RessourcePlanner pour l'activer.",
                type="positive" if saved == PURE_MODE else "warning",
            )
            self.render_content.refresh()

        if configured != PURE_MODE:
            ui.button(
                "Activer le moteur pur au prochain redémarrage",
                icon="rocket_launch",
                on_click=lambda: choose_mode(PURE_MODE),
            ).props("unelevated no-caps color=primary")
        else:
            ui.label("✓ Le mode pur est configuré.").classes("text-sm text-green-700")

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
            "aucun projet, technicien, demande, localisation ou contenu du classeur. "
            "Il confirme que le chemin pure a tourné, mais ne remplace pas la validation "
            "fonctionnelle des scénarios de #56."
        ).classes("text-xs muted")

        with ui.expansion("Rollback diagnostic temporaire", icon="history").classes("w-full"):
            ui.label(
                "À utiliser seulement si une régression métier est constatée pendant la validation."
            ).classes("text-xs text-amber-700")
            with ui.row().classes("gap-2"):
                ui.button(
                    "guarded_pure",
                    on_click=lambda: choose_mode(GUARDED_PURE_MODE),
                ).props("outline no-caps")
                ui.button(
                    "legacy",
                    on_click=lambda: choose_mode(LEGACY_MODE),
                ).props("outline no-caps color=negative")


def install_pure_validation_ui() -> None:
    """Add explicit production-cutover controls and technical pure-cycle evidence."""
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

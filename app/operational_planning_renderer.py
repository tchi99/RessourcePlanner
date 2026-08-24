from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from . import ui as ui_module


PlanningRenderer = Callable[[ui_module.PlannerUI], None]
BasePlanningRenderer = Callable[..., None]
WeeklyStatsProvider = Callable[[Any, Any], dict[str, dict[str, float]]]
RankWeeklyStats = Callable[
    [ui_module.PlannerUI, WeeklyStatsProvider, Any, Any],
    dict[str, dict[str, float]],
]
OwnerCallback = Callable[[ui_module.PlannerUI], Any]


def compose_operational_planning_renderer(
    *,
    base_render: BasePlanningRenderer,
    weekly_stats_provider: WeeklyStatsProvider,
    rank_weekly_stats: RankWeeklyStats,
    register_manual_order_handler: OwnerCallback,
    manual_order_script: Callable[[ui_module.PlannerUI], str],
) -> PlanningRenderer:
    """Compose le renderer opérationnel final sans réécrire les couches V1.x."""

    def render_planning(owner: ui_module.PlannerUI) -> None:
        register_manual_order_handler(owner)

        def ranked_stats(repo: Any, week: Any) -> dict[str, dict[str, float]]:
            return rank_weekly_stats(owner, weekly_stats_provider, repo, week)

        base_render(owner, weekly_stats_provider=ranked_stats)

        # Les flèches sont ajoutées uniquement lorsque « Ordre manuel » est actif.
        ui.timer(0.10, lambda: ui.run_javascript(manual_order_script(owner)), once=True)

    return render_planning

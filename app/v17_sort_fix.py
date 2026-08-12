from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v17_refinements


def install_v17_sort_fix() -> None:
    """Corrige le tri des ressources sans forcer un nouveau rendu du planning.

    Le premier mécanisme V1.7 changeait le mode de tri puis appelait
    ``render_content.refresh()``. Le rendu Python reconstruisait alors les groupes dans
    leur ordre historique (disponibilité décroissante) avant que le tri navigateur ne
    soit appliqué, ce qui pouvait annuler visuellement le choix de l'utilisateur.

    Le mode choisi est maintenant mémorisé sur PlannerUI et le DOM déjà affiché est
    réordonné immédiatement. Les rafraîchissements suivants réappliquent toujours ce
    même mode via le helper V1.7 existant.
    """
    if getattr(ui_module.PlannerUI, "_v17_sort_fix_installed", False):
        return

    def set_resource_sort(self: ui_module.PlannerUI, value: Any) -> None:
        mode = str(value or v17_refinements.SORT_AVAIL_DESC)
        if mode not in v17_refinements.SORT_OPTIONS:
            mode = v17_refinements.SORT_AVAIL_DESC
        self.planning_resource_sort = mode

        # Ne pas rafraîchir tout le composant : cela évite de reconstruire les lignes
        # dans le tri par disponibilité avant l'application du nouveau choix.
        script = v17_refinements._resource_sort_script(self)
        ui.run_javascript(script)
        # Une seconde passe couvre les quelques cas où Quasar termine une mise en page
        # juste après l'événement de sélection.
        ui.timer(0.12, lambda: ui.run_javascript(v17_refinements._resource_sort_script(self)), once=True)

    v17_refinements._set_resource_sort = set_resource_sort
    ui_module.PlannerUI._v17_sort_fix_installed = True

from __future__ import annotations

import json
import unicodedata
from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v15, v15_refinements, v16, v16_refinements, v17, v17_refinements
from .bugfixes import schedulable_technicians


MANUAL_ORDER_EVENT = "v17-manual-resource-order"


def _alpha_key(value: Any) -> str:
    """Clé alphabétique française sans distinction d'accents.

    É/È/Ê sont donc classés avec E, À/Â avec A, Ç avec C, etc. La casse est
    également ignorée. Le nom original reste uniquement un dernier critère stable.
    """
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


class _RankedFree(float):
    """Float normal à l'affichage, mais portant un rang pour le tri V1.7.

    Le renderer historique de ``v17`` trie toujours sur ``-prudent_free``. En
    remplaçant temporairement cette valeur par ce sous-type, on peut lui fournir le
    rang réellement demandé sans falsifier les heures affichées ou les calculs de
    capacité.
    """

    def __new__(cls, value: Any, rank: int) -> "_RankedFree":
        obj = float.__new__(cls, float(value or 0.0))
        obj.rank = int(rank)
        return obj

    def __neg__(self) -> int:
        return self.rank


def _ranked_weekly_stats(
    self: ui_module.PlannerUI,
    original_stats: Any,
    repo: Any,
    week: Any,
) -> dict[str, dict[str, float]]:
    stats = original_stats(repo, week)
    if repo is not self.repo:
        return stats

    mode = str(
        getattr(self, "planning_resource_sort", v17_refinements.SORT_AVAIL_DESC)
        or v17_refinements.SORT_AVAIL_DESC
    )
    if mode not in v17_refinements.SORT_OPTIONS:
        mode = v17_refinements.SORT_AVAIL_DESC

    manual = v17_refinements._resource_order_map(repo)
    names = list(stats)

    def key(name: str) -> tuple[Any, ...]:
        free = float(stats.get(name, {}).get("prudent_free", 0.0) or 0.0)
        alpha = _alpha_key(name)
        if mode == v17_refinements.SORT_AVAIL_ASC:
            return (free, alpha, str(name).casefold())
        if mode == v17_refinements.SORT_ALPHA_ASC:
            return (alpha, str(name).casefold())
        if mode == v17_refinements.SORT_ALPHA_DESC:
            # Le renversement est appliqué plus bas pour conserver un tri accent-insensible.
            return (alpha, str(name).casefold())
        if mode == v17_refinements.SORT_MANUAL:
            order = manual.get(name)
            return (
                0 if order is not None else 1,
                float(order) if order is not None else 0.0,
                alpha,
                str(name).casefold(),
            )
        return (-free, alpha, str(name).casefold())

    ordered = sorted(
        names,
        key=key,
        reverse=(mode == v17_refinements.SORT_ALPHA_DESC),
    )
    ranks = {name: index for index, name in enumerate(ordered)}

    result: dict[str, dict[str, float]] = {}
    for name, values in stats.items():
        copy = dict(values)
        copy["prudent_free"] = _RankedFree(
            values.get("prudent_free", 0.0),
            ranks.get(name, len(ranks)),
        )
        result[name] = copy
    return result


def _set_resource_sort(self: ui_module.PlannerUI, value: Any) -> None:
    mode = str(value or v17_refinements.SORT_AVAIL_DESC)
    if mode not in v17_refinements.SORT_OPTIONS:
        mode = v17_refinements.SORT_AVAIL_DESC
    self.planning_resource_sort = mode
    # Le tri est maintenant effectué côté Python avant la construction de la grille.
    # Un vrai rafraîchissement est donc nécessaire et ne dépend plus d'un déplacement
    # fragile des éléments DOM après leur rendu par Quasar.
    self.render_content.refresh()


def _manual_order_script(self: ui_module.PlannerUI) -> str:
    mode = str(
        getattr(self, "planning_resource_sort", v17_refinements.SORT_AVAIL_DESC)
        or v17_refinements.SORT_AVAIL_DESC
    )
    names = sorted(
        [str(row.get("name") or "").strip() for row in schedulable_technicians(self.repo)],
        key=len,
        reverse=True,
    )
    mode_json = json.dumps(mode, ensure_ascii=False)
    names_json = json.dumps(names, ensure_ascii=False)
    event_json = json.dumps(MANUAL_ORDER_EVENT)

    return f"""
(() => {{
  const mode = {mode_json};
  const names = {names_json};
  const eventName = {event_json};

  document.querySelectorAll('.v17-manual-order-controls').forEach(node => node.remove());
  if (mode !== 'manual') return;

  const resourceName = cell => {{
    const text = (cell?.textContent || '').trim();
    return names.find(name => text.startsWith(name)) || '';
  }};

  document.querySelectorAll('.resource-cell').forEach(cell => {{
    const technician = resourceName(cell);
    if (!technician) return;

    const controls = document.createElement('div');
    controls.className = 'v17-manual-order-controls';
    controls.style.cssText = 'display:flex;gap:3px;margin-top:3px;align-items:center;';

    const makeButton = (symbol, direction, title) => {{
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = symbol;
      button.title = title;
      button.style.cssText = [
        'width:25px','height:23px','line-height:18px','border:1px solid #cbd5e1',
        'border-radius:5px','background:#fff','cursor:pointer','font-weight:700'
      ].join(';');
      button.addEventListener('click', event => {{
        event.preventDefault();
        event.stopPropagation();
        emitEvent(eventName, {{technician, direction}});
      }});
      return button;
    }};

    controls.appendChild(makeButton('↑', -1, 'Monter cette ressource'));
    controls.appendChild(makeButton('↓', 1, 'Descendre cette ressource'));
    cell.appendChild(controls);
  }});
}})();
"""


def _move_manual_resource(
    self: ui_module.PlannerUI,
    technician: str,
    direction: int,
) -> None:
    if str(getattr(self, "planning_resource_sort", "")) != v17_refinements.SORT_MANUAL:
        return

    name = str(technician or "").strip()
    if not name or direction not in {-1, 1}:
        return

    class_map = v16.resource_class_map(self.repo)
    group = class_map.get(name, v16.UNCLASSIFIED)
    manual = v17_refinements._resource_order_map(self.repo)
    profiles = v16_refinements.resource_profile_map(self.repo)

    group_names = [
        str(row.get("name") or "").strip()
        for row in schedulable_technicians(self.repo)
        if class_map.get(str(row.get("name") or "").strip(), v16.UNCLASSIFIED) == group
    ]
    group_names.sort(
        key=lambda item: (
            0 if item in manual else 1,
            manual.get(item, 0.0),
            _alpha_key(item),
            item.casefold(),
        )
    )

    try:
        index = group_names.index(name)
    except ValueError:
        return
    target = index + direction
    if target < 0 or target >= len(group_names):
        ui.notify(
            "Cette ressource est déjà en première position."
            if direction < 0
            else "Cette ressource est déjà en dernière position.",
            type="info",
        )
        return

    group_names[index], group_names[target] = group_names[target], group_names[index]

    try:
        for position, resource_name in enumerate(group_names, start=1):
            profile = profiles.get(resource_name, {})
            resource_class = profile.get("class")
            if resource_class == v16.UNCLASSIFIED:
                resource_class = None
            v16_refinements.update_resource_profile(
                self.repo,
                resource_name,
                resource_class,
                profile.get("competencies") or [],
                str(profile.get("note") or ""),
                position * 10,
            )
        self._after_write(f"{name} déplacé dans l'ordre manuel")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _register_manual_order_handler(self: ui_module.PlannerUI) -> None:
    if getattr(self, "_v17_manual_order_handler_registered", False):
        return

    def handler(event: Any) -> None:
        args = getattr(event, "args", {}) or {}
        try:
            direction = int(args.get("direction") or 0)
        except (TypeError, ValueError):
            direction = 0
        _move_manual_resource(
            self,
            str(args.get("technician") or ""),
            direction,
        )

    ui.on(MANUAL_ORDER_EVENT, handler)
    self._v17_manual_order_handler_registered = True


def install_v17_sort_fix() -> None:
    """Tri fiable côté Python + ordre manuel directement dans la grille."""
    if getattr(ui_module.PlannerUI, "_v17_sort_fix_installed", False):
        return

    # Désactive l'ancien tri DOM. Il était vulnérable au re-render de Quasar et
    # expliquait pourquoi le calendrier revenait visuellement à « plus disponible ».
    v17_refinements._resource_sort_script = lambda _self: "void 0;"
    v17_refinements._set_resource_sort = _set_resource_sort

    base_render = v17_refinements._render_planning
    original_weekly_stats = v16._weekly_resource_stats

    def render_planning(self: ui_module.PlannerUI) -> None:
        _register_manual_order_handler(self)

        def ranked_stats(repo: Any, week: Any) -> dict[str, dict[str, float]]:
            return _ranked_weekly_stats(self, original_weekly_stats, repo, week)

        base_render(self, weekly_stats_provider=ranked_stats)

        # Les flèches sont ajoutées uniquement lorsque « Ordre manuel » est actif.
        ui.timer(0.10, lambda: ui.run_javascript(_manual_order_script(self)), once=True)

    ui_module.PlannerUI.render_planning = render_planning
    v13._render_operational_planning = render_planning
    v15._render_operational_planning_v15 = render_planning
    v15_refinements._render_planning = render_planning
    v16._render_planning_v16 = render_planning
    v16_refinements._render_planning = render_planning
    v17_refinements._render_planning = render_planning

    ui_module.PlannerUI.move_resource_manual = _move_manual_resource
    ui_module.PlannerUI._v17_sort_fix_installed = True

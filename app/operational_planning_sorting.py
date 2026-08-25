from __future__ import annotations

import json
import unicodedata
from typing import Any, Callable, Iterable


SORT_AVAIL_DESC = "availability_desc"
SORT_AVAIL_ASC = "availability_asc"
SORT_ALPHA_ASC = "alpha_asc"
SORT_ALPHA_DESC = "alpha_desc"
SORT_MANUAL = "manual"
SORT_OPTIONS = {
    SORT_AVAIL_DESC: "Disponibilité — plus disponible d'abord",
    SORT_AVAIL_ASC: "Disponibilité — plus occupé d'abord",
    SORT_ALPHA_ASC: "Alphabétique A → Z",
    SORT_ALPHA_DESC: "Alphabétique Z → A",
    SORT_MANUAL: "Ordre manuel",
}

# Keep the historical browser event name for compatibility with already-rendered pages.
MANUAL_ORDER_EVENT = "v17-manual-resource-order"

OrderMapProvider = Callable[[Any], dict[str, float]]
WeeklyStatsProvider = Callable[[Any, Any], dict[str, dict[str, float]]]


def alpha_key(value: Any) -> str:
    """Return an accent-insensitive, case-insensitive French alphabetical key."""

    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


class RankedFree(float):
    """Display the real free hours while exposing a deterministic Python sort rank."""

    def __new__(cls, value: Any, rank: int) -> "RankedFree":
        obj = float.__new__(cls, float(value or 0.0))
        obj.rank = int(rank)
        return obj

    def __neg__(self) -> int:
        return self.rank


def resource_sort_mode(owner: Any) -> str:
    mode = str(getattr(owner, "planning_resource_sort", SORT_AVAIL_DESC) or SORT_AVAIL_DESC)
    return mode if mode in SORT_OPTIONS else SORT_AVAIL_DESC


def rank_weekly_stats(
    owner: Any,
    original_stats: WeeklyStatsProvider,
    repo: Any,
    week: Any,
    *,
    order_map: OrderMapProvider,
) -> dict[str, dict[str, float]]:
    """Rank resource stats according to the active operational-planning sort mode."""

    stats = original_stats(repo, week)
    if repo is not getattr(owner, "repo", None):
        return stats

    mode = resource_sort_mode(owner)
    manual = order_map(repo)
    names = list(stats)

    def key(name: str) -> tuple[Any, ...]:
        free = float(stats.get(name, {}).get("prudent_free", 0.0) or 0.0)
        alpha = alpha_key(name)
        if mode == SORT_AVAIL_ASC:
            return (free, alpha, str(name).casefold())
        if mode == SORT_ALPHA_ASC:
            return (alpha, str(name).casefold())
        if mode == SORT_ALPHA_DESC:
            return (alpha, str(name).casefold())
        if mode == SORT_MANUAL:
            order = manual.get(name)
            return (
                0 if order is not None else 1,
                float(order) if order is not None else 0.0,
                alpha,
                str(name).casefold(),
            )
        return (-free, alpha, str(name).casefold())

    ordered = sorted(names, key=key, reverse=(mode == SORT_ALPHA_DESC))
    ranks = {name: index for index, name in enumerate(ordered)}

    result: dict[str, dict[str, float]] = {}
    for name, values in stats.items():
        copy = dict(values)
        copy["prudent_free"] = RankedFree(
            values.get("prudent_free", 0.0),
            ranks.get(name, len(ranks)),
        )
        result[name] = copy
    return result


def set_resource_sort(owner: Any, value: Any) -> None:
    mode = str(value or SORT_AVAIL_DESC)
    if mode not in SORT_OPTIONS:
        mode = SORT_AVAIL_DESC
    owner.planning_resource_sort = mode
    owner.render_content.refresh()


def manual_order_script(owner: Any, technicians: Iterable[str]) -> str:
    """Build the browser helper that exposes up/down controls in manual sort mode."""

    mode = resource_sort_mode(owner)
    names = sorted(
        [str(name or "").strip() for name in technicians if str(name or "").strip()],
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

from __future__ import annotations

from typing import Any

from nicegui import ui

from . import operational_planning_header_filters as header_filters_module
from .operational_planning_orchestrator import render_operational_planning
from .operational_planning_sorting import SORT_OPTIONS, resource_sort_mode, set_resource_sort
from .ui_context import ensure_scoped_ui


SCROLL_SETUP_JS = r"""
(() => {
  const PAGE_KEY = 'planner:v17:planning:windowY';
  const GRID_KEY = 'planner:v17:planning:gridScroll';
  const PENDING_KEY = 'planner:v17:planning:pendingCollapsed';

  const install = () => {
    const savedWindowY = Number(sessionStorage.getItem(PAGE_KEY) || 0);
    if (savedWindowY > 0) window.scrollTo({top: savedWindowY, behavior: 'instant'});
    if (!window.__plannerV17WindowScrollInstalled) {
      window.addEventListener('scroll', () => {
        sessionStorage.setItem(PAGE_KEY, String(window.scrollY || 0));
      }, {passive: true});
      window.__plannerV17WindowScrollInstalled = true;
    }

    const scrollRoot = [...document.querySelectorAll('.q-scrollarea')]
      .find(el => el.querySelector('.schedule-grid'));
    const scrollContainer = scrollRoot?.querySelector('.q-scrollarea__container');
    if (scrollContainer) {
      let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(GRID_KEY) || '{}'); } catch (_) {}
      if (Number.isFinite(Number(saved.top))) scrollContainer.scrollTop = Number(saved.top);
      if (Number.isFinite(Number(saved.left))) scrollContainer.scrollLeft = Number(saved.left);
      if (!scrollContainer.dataset.v17ScrollTracking) {
        scrollContainer.dataset.v17ScrollTracking = '1';
        scrollContainer.addEventListener('scroll', () => {
          sessionStorage.setItem(GRID_KEY, JSON.stringify({
            top: scrollContainer.scrollTop || 0,
            left: scrollContainer.scrollLeft || 0,
          }));
        }, {passive: true});
      }
    }

    const cards = [...document.querySelectorAll('.q-card')];
    const pendingCard = cards.find(card =>
      (card.textContent || '').includes("En attente d'approbation dans cette semaine")
    );
    if (pendingCard && !pendingCard.dataset.v17Collapsible) {
      pendingCard.dataset.v17Collapsible = '1';
      const directChildren = [...pendingCard.children];
      const titleHost = directChildren.find(child =>
        (child.textContent || '').includes("En attente d'approbation dans cette semaine")
      ) || directChildren[0];

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'v17-pending-toggle';
      button.style.cssText = [
        'align-self:flex-start',
        'border:1px solid #cbd5e1',
        'border-radius:6px',
        'padding:4px 10px',
        'font-size:12px',
        'background:white',
        'cursor:pointer',
        'margin-left:auto'
      ].join(';');
      pendingCard.insertBefore(button, pendingCard.children[1] || null);

      const apply = collapsed => {
        directChildren.forEach(child => {
          if (child !== titleHost) child.style.display = collapsed ? 'none' : '';
        });
        button.textContent = collapsed ? 'Afficher' : 'Réduire';
        button.title = collapsed
          ? "Afficher les demandes en attente d'approbation"
          : "Réduire les demandes en attente d'approbation";
        pendingCard.style.paddingBottom = collapsed ? '10px' : '';
        sessionStorage.setItem(PENDING_KEY, collapsed ? '1' : '0');
      };

      let collapsed = sessionStorage.getItem(PENDING_KEY) === '1';
      apply(collapsed);
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        collapsed = !collapsed;
        apply(collapsed);
      });
    }
  };

  requestAnimationFrame(() => requestAnimationFrame(install));
  setTimeout(install, 120);
})();
"""


def install_planning_browser_helpers() -> None:
    ui.run_javascript(SCROLL_SETUP_JS)


def render_operational_planning_base(
    owner: Any,
    *,
    weekly_stats_provider: Any | None = None,
    bindings: Any,
) -> None:
    """Render the stable operational-planning shell around the orchestrator."""

    sort_mode = resource_sort_mode(owner)
    scoped_ui = ensure_scoped_ui(
        header_filters_module,
        scope_name="operational_planning_header_filters",
        scoped_factories=("select",),
    )
    original_select = scoped_ui.base_factory("select")

    def select_proxy(options: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("label") == "Classe":
            original_select(
                SORT_OPTIONS,
                label="Tri des ressources",
                value=sort_mode,
                on_change=lambda event: set_resource_sort(owner, event.value),
            ).classes("min-w-[240px]")
        return original_select(options, *args, **kwargs)

    with scoped_ui.override_factory("select", select_proxy):
        render_operational_planning(
            owner,
            weekly_stats_provider=weekly_stats_provider,
            bindings=bindings,
        )

    ui.timer(0.08, install_planning_browser_helpers, once=True)

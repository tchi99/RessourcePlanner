from __future__ import annotations

from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from nicegui import ui

from . import v13, v14, v15_refinements, v16
from .excel_repository import ExcelRepository


SelectOverride = Callable[[Callable[..., Any], tuple[Any, ...], dict[str, Any]], Any]


class _ContextualSelectUI:
    """Delegate NiceGUI calls while allowing task-local ``select`` decoration.

    Historical dialogs sometimes need to decorate one specific select created deep in
    an older renderer. Replacing ``nicegui.ui.select`` globally makes concurrent page
    renders interfere with each other. This facade is installed only in the target
    legacy module and stores the temporary select behavior in a ``ContextVar`` so each
    async/client context sees its own override.
    """

    _v18_contextual_select_facade = True

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self._select_override: ContextVar[SelectOverride | None] = ContextVar(
            "v18_segment_dialog_select_override",
            default=None,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def select(self, *args: Any, **kwargs: Any) -> Any:
        override = self._select_override.get()
        if override is None:
            return self._delegate.select(*args, **kwargs)
        return override(self._delegate.select, args, kwargs)

    @contextmanager
    def override_select(self, override: SelectOverride) -> Iterator[None]:
        token = self._select_override.set(override)
        try:
            yield
        finally:
            self._select_override.reset(token)


def _install_approval_batching() -> None:
    """Coalesce the complete approval workflow behind one physical Excel save.

    The V1.5 approval workflow can update the demand, synchronize one or more
    segments and rebuild AllocationsMO. Each of those historical helpers requests a
    save. V1.7.1 already knows how to defer saves; this wrapper simply makes the
    complete approval one logical write batch so nested save requests collapse to a
    single workbook save.
    """
    if getattr(ExcelRepository, "_v18_approval_batching_installed", False):
        return

    original_approve = ExcelRepository.approve_demand

    def approve_demand(
        self: ExcelRepository, number: str, comment: str = ""
    ) -> None:
        batch_factory = getattr(self, "batch_update", None)
        context = (
            batch_factory("approve demand")
            if callable(batch_factory)
            else nullcontext(self)
        )
        with context:
            original_approve(self, number, comment)

    ExcelRepository.approve_demand = approve_demand
    ExcelRepository._v18_approval_batching_installed = True


def _install_skill_class_precedence() -> None:
    """Prefer an explicit installation label over the generic automation keyword.

    Configuration values such as ``Installation automatisation`` contain both
    ``installation`` and ``automatis...``. The original classifier checked the
    automation keyword first and therefore mapped those skills to Programmation.
    An explicit installation wording is more specific and must win.
    """
    if getattr(v16, "_v18_skill_class_precedence_installed", False):
        return

    original_normalize = v16._normalize_resource_class

    def normalize_resource_class(value: Any) -> str | None:
        text = v16._normalized_text(value)
        if "installation" in text or "installateur" in text:
            return "Installation"
        return original_normalize(value)

    v16._normalize_resource_class = normalize_resource_class
    v16._v18_skill_class_precedence_installed = True


def _open_parent_demand(self: Any, number: str) -> None:
    demand = next(
        (
            row
            for row in self.repo.demands()
            if str(row.get("NoDemande") or "") == str(number)
        ),
        None,
    )
    if not demand:
        ui.notify("Demande associée introuvable.", type="warning")
        return
    self.open_edit_request_dialog(demand)


def _install_segment_parent_navigation() -> None:
    """Add an open-parent icon to the Demand field of an existing segment dialog."""
    if getattr(v15_refinements, "_v18_parent_navigation_installed", False):
        return

    original_segment_dialog = v15_refinements._segment_dialog

    current_ui = v15_refinements.ui
    if not getattr(current_ui, "_v18_contextual_select_facade", False):
        current_ui = _ContextualSelectUI(current_ui)
        v15_refinements.ui = current_ui

    def segment_dialog(
        self: Any,
        segment: dict[str, Any] | None = None,
        demand_number: str | None = None,
    ) -> None:
        if not segment:
            original_segment_dialog(self, segment=segment, demand_number=demand_number)
            return

        parent_number = str(segment.get("NoDemande") or demand_number or "")

        def select_with_parent_link(
            original_select: Callable[..., Any],
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:
            component = original_select(*args, **kwargs)
            label = str(kwargs.get("label") or "")
            if label == "Demande MO" and parent_number:
                component.props("append-icon=open_in_new")
                component.on(
                    "click:append",
                    lambda _event: _open_parent_demand(self, parent_number),
                )
                component.tooltip("Ouvrir et modifier la demande associée")
            return component

        with current_ui.override_select(select_with_parent_link):
            original_segment_dialog(
                self, segment=segment, demand_number=demand_number
            )

    v15_refinements._segment_dialog = segment_dialog
    v13._open_segment_dialog = segment_dialog
    v14._open_segment_dialog_v14 = segment_dialog
    v15_refinements._v18_parent_navigation_installed = True


def install_v18_workflow_fixes() -> None:
    _install_approval_batching()
    _install_skill_class_precedence()
    _install_segment_parent_navigation()

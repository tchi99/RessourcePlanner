from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from nicegui import ui

from . import features, v14_engine, v16, v16_refinements
from . import operational_planning_drop_handler as drop_handler_module
from . import operational_planning_sorting as planning_sorting
from . import operational_planning_sorting_compat as sorting_compat
from . import resource_management_compat as resource_management
from . import ui as ui_module
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository


AVAILABILITY_CACHE_SECONDS = 1.0


def _path_marker(repo: ExcelRepository, *parts: Any) -> tuple[Any, ...]:
    return (str(repo.path or ""), *parts)


def _invalidate_runtime_caches(repo: ExcelRepository) -> None:
    repo._v171_cache_epoch = int(getattr(repo, "_v171_cache_epoch", 0)) + 1


def _suspend_excel_ui(repo: ExcelRepository) -> dict[str, Any]:
    state: dict[str, Any] = {}
    try:
        app = repo._book().app
    except Exception:
        return state

    state["app"] = app
    for attribute in ("screen_updating", "calculation"):
        try:
            state[attribute] = getattr(app, attribute)
        except Exception:
            pass

    try:
        app.screen_updating = False
    except Exception:
        pass
    try:
        app.calculation = "manual"
    except Exception:
        pass
    try:
        state["enable_events"] = bool(app.api.EnableEvents)
        app.api.EnableEvents = False
    except Exception:
        pass
    return state


def _restore_excel_ui(state: dict[str, Any]) -> None:
    app = state.get("app")
    if app is None:
        return
    try:
        if "enable_events" in state:
            app.api.EnableEvents = state["enable_events"]
    except Exception:
        pass
    try:
        if "calculation" in state:
            app.calculation = state["calculation"]
    except Exception:
        pass
    try:
        if "screen_updating" in state:
            app.screen_updating = state["screen_updating"]
    except Exception:
        pass


def _install_repository_batching() -> None:
    if getattr(ExcelRepository, "_v171_batching_installed", False):
        return

    original_save = ExcelRepository.save
    original_create_demand = ExcelRepository.create_demand
    original_update_demand = ExcelRepository.update_demand

    def save(self: ExcelRepository) -> None:
        _invalidate_runtime_caches(self)
        if int(getattr(self, "_v171_batch_depth", 0)) > 0:
            self._v171_batch_dirty = True
            self._v171_deferred_save_requests = int(
                getattr(self, "_v171_deferred_save_requests", 0)
            ) + 1
            return

        started = time.perf_counter()
        original_save(self)
        elapsed = time.perf_counter() - started
        self._v171_last_save_seconds = elapsed
        self._v171_actual_save_count = int(getattr(self, "_v171_actual_save_count", 0)) + 1

    @contextmanager
    def batch_update(self: ExcelRepository, label: str = "Excel batch"):
        with self._lock:
            outermost = int(getattr(self, "_v171_batch_depth", 0)) == 0
            if outermost:
                self._v171_batch_dirty = False
                self._v171_deferred_save_requests = 0
                self._v171_batch_started = time.perf_counter()
                self._v171_batch_label = str(label or "Excel batch")
                self._v171_excel_state = _suspend_excel_ui(self)

            self._v171_batch_depth = int(getattr(self, "_v171_batch_depth", 0)) + 1
            try:
                yield self
            finally:
                self._v171_batch_depth = max(
                    int(getattr(self, "_v171_batch_depth", 1)) - 1,
                    0,
                )
                if outermost:
                    _restore_excel_ui(getattr(self, "_v171_excel_state", {}))
                    save_seconds = 0.0
                    if bool(getattr(self, "_v171_batch_dirty", False)):
                        save_started = time.perf_counter()
                        original_save(self)
                        save_seconds = time.perf_counter() - save_started
                        self._v171_actual_save_count = int(
                            getattr(self, "_v171_actual_save_count", 0)
                        ) + 1

                    total_seconds = time.perf_counter() - float(
                        getattr(self, "_v171_batch_started", time.perf_counter())
                    )
                    metrics = {
                        "label": str(getattr(self, "_v171_batch_label", label)),
                        "total_seconds": round(total_seconds, 4),
                        "save_seconds": round(save_seconds, 4),
                        "deferred_save_requests": int(
                            getattr(self, "_v171_deferred_save_requests", 0)
                        ),
                        "actual_saves": 1
                        if bool(getattr(self, "_v171_batch_dirty", False))
                        and self.save_on_write
                        else 0,
                    }
                    self._v171_last_batch_metrics = metrics
                    self._v171_last_save_seconds = save_seconds
                    self._v171_batch_dirty = False
                    self._v171_excel_state = {}
                    if total_seconds >= 1.0:
                        print(
                            "Excel performance "
                            f"[{metrics['label']}]: total={total_seconds:.2f}s, "
                            f"save={save_seconds:.2f}s, "
                            f"save requests={metrics['deferred_save_requests']} -> "
                            f"actual={metrics['actual_saves']}"
                        )

    def performance_snapshot(self: ExcelRepository) -> dict[str, Any]:
        return {
            "last_batch": dict(getattr(self, "_v171_last_batch_metrics", {}) or {}),
            "last_save_seconds": round(
                float(getattr(self, "_v171_last_save_seconds", 0.0) or 0.0), 4
            ),
            "actual_save_count": int(getattr(self, "_v171_actual_save_count", 0)),
        }

    def create_demand_batched(
        self: ExcelRepository, data: dict[str, Any], submit: bool = False
    ) -> str:
        with self.batch_update("create demand"):
            return original_create_demand(self, data, submit)

    def update_demand_batched(
        self: ExcelRepository,
        number: str,
        updates: dict[str, Any],
        action: str = "Modification",
        comment: str = "",
    ) -> None:
        with self.batch_update("update demand"):
            original_update_demand(self, number, updates, action, comment)

    ExcelRepository.save = save
    ExcelRepository.batch_update = batch_update
    ExcelRepository.performance_snapshot = performance_snapshot
    ExcelRepository.create_demand = create_demand_batched
    ExcelRepository.update_demand = update_demand_batched
    ExcelRepository._v171_batching_installed = True


def _install_availability_optimizations() -> None:
    if getattr(features, "_v171_availability_installed", False):
        return

    original_ensure = features._ensure_availability_sheet
    original_records = features.availability_records
    original_initialize = features.initialize_standard_schedules

    def ensure_availability_sheet(repo: ExcelRepository) -> None:
        marker = _path_marker(repo, tuple(features.AVAILABILITY_HEADERS))
        if getattr(repo, "_v171_availability_ready", None) == marker:
            return
        with repo.batch_update("availability setup"):
            original_ensure(repo)
        repo._v171_availability_ready = marker

    def availability_records_cached(repo: ExcelRepository) -> list[dict[str, Any]]:
        epoch = int(getattr(repo, "_v171_cache_epoch", 0))
        now = time.monotonic()
        cache = getattr(repo, "_v171_availability_cache", None)
        if cache:
            cache_epoch, cached_at, rows = cache
            if cache_epoch == epoch and now - cached_at <= AVAILABILITY_CACHE_SECONDS:
                return [dict(row) for row in rows]

        rows = original_records(repo)
        stored = [dict(row) for row in rows]
        repo._v171_availability_cache = (epoch, now, stored)
        return [dict(row) for row in stored]

    def initialize_standard_schedules_batched(repo: ExcelRepository) -> int:
        with repo.batch_update("initialize standard schedules"):
            return original_initialize(repo)

    features._ensure_availability_sheet = ensure_availability_sheet
    features.availability_records = availability_records_cached
    features.initialize_standard_schedules = initialize_standard_schedules_batched
    features._v171_availability_installed = True


def _install_schema_ensure_optimizations() -> None:
    if getattr(v14_engine, "_v171_schema_ensure_installed", False):
        return

    original_v14_ensure = v14_engine.ensure_v14_sheets
    original_profile_ensure = v16_refinements.ensure_resource_profiles

    def ensure_v14_sheets(repo: ExcelRepository) -> None:
        marker = _path_marker(
            repo,
            tuple(v14_engine.SEGMENT_EXTRA_HEADERS),
            tuple(v14_engine.ALLOCATION_HEADERS),
        )
        if getattr(repo, "_v171_v14_ready", None) == marker:
            return
        with repo.batch_update("V1.4 schema setup"):
            original_v14_ensure(repo)
        repo._v171_v14_ready = marker

    def ensure_resource_profiles(repo: ExcelRepository) -> None:
        marker = _path_marker(repo, tuple(v16_refinements.RESOURCE_PROFILE_HEADERS))
        if getattr(repo, "_v171_resource_profiles_ready", None) == marker:
            return
        with repo.batch_update("resource profile setup"):
            original_profile_ensure(repo)
        repo._v171_resource_profiles_ready = marker

    v14_engine.ensure_v14_sheets = ensure_v14_sheets
    v16_refinements.ensure_resource_profiles = ensure_resource_profiles
    v14_engine._v171_schema_ensure_installed = True


def _order_number(value: Any) -> float | None:
    return resource_management._order_number(value)


def _write_order_column(repo: ExcelRepository, updates: dict[str, Any]) -> bool:
    v16_refinements.ensure_resource_profiles(repo)
    rows = v16_refinements._profile_records(repo)
    if not rows:
        return False

    try:
        order_col = v16_refinements.RESOURCE_PROFILE_HEADERS.index(
            resource_management.RESOURCE_ORDER_FIELD
        ) + 1
    except ValueError:
        return False

    row_map = {int(row["_row"]): row for row in rows if row.get("_row")}
    max_row = max(row_map)
    changed = False
    matrix: list[list[Any]] = []

    for excel_row in range(2, max_row + 1):
        record = row_map.get(excel_row)
        if record is None:
            matrix.append([None])
            continue
        name = str(record.get("Technicien") or "").strip()
        current = _order_number(record.get(resource_management.RESOURCE_ORDER_FIELD))
        requested = _order_number(updates[name]) if name in updates else current
        if requested != current:
            changed = True
        matrix.append([requested])

    if not changed:
        return False

    with repo.batch_update("resource manual order"):
        sheet = repo._book().sheets[v16_refinements.RESOURCE_PROFILE_SHEET]
        sheet.range((2, order_col), (max_row, order_col)).value = matrix
        repo.save()
    return True


def _manual_order_dialog_fast(self: ui_module.PlannerUI) -> None:
    self.interaction_lock = True
    resource_management._ensure_manual_order_column(self.repo)
    profiles = v16_refinements.resource_profile_map(self.repo)
    technicians = sorted(
        self.repo.technicians(),
        key=lambda row: planning_sorting.alpha_key(str(row.get("name") or "")),
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label("Ordre manuel des ressources").classes("text-xl font-bold")
        ui.label(
            "Les positions sont enregistrées en une seule écriture Excel afin d'éviter "
            "une sauvegarde par ressource."
        ).classes("text-sm muted")

        controls: dict[str, Any] = {}
        for technician in technicians:
            name = str(technician.get("name") or "").strip()
            if not name:
                continue
            profile = profiles.get(name, {})
            with ui.row().classes("w-full items-center gap-3"):
                ui.label(name).classes("flex-1 font-medium")
                ui.label(str(profile.get("class") or v16.UNCLASSIFIED)).classes(
                    "w-[170px] text-xs muted"
                )
                controls[name] = ui.number(
                    "Ordre",
                    value=_order_number(profile.get("order")),
                    min=0,
                    step=1,
                ).classes("w-[130px]")

        def alpha_values() -> None:
            ordered_names = sorted(controls, key=planning_sorting.alpha_key)
            for index, name in enumerate(ordered_names, start=1):
                controls[name].value = index * 10

        def save() -> None:
            try:
                updates = {name: control.value for name, control in controls.items()}
                _write_order_column(self.repo, updates)
                dialog.close()
                self._after_write("Ordre manuel des ressources enregistré")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-between"):
            ui.button(
                "Préremplir A → Z", icon="sort_by_alpha", on_click=alpha_values
            ).props("outline no-caps")
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
                ui.button("Enregistrer", icon="save", on_click=save).props(
                    "unelevated no-caps color=primary"
                )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _move_manual_resource_fast(
    self: ui_module.PlannerUI,
    technician: str,
    direction: int,
) -> None:
    if str(getattr(self, "planning_resource_sort", "")) != planning_sorting.SORT_MANUAL:
        return

    name = str(technician or "").strip()
    if not name or direction not in {-1, 1}:
        return

    class_map = v16.resource_class_map(self.repo)
    group = class_map.get(name, v16.UNCLASSIFIED)
    manual = resource_management._resource_order_map(self.repo)

    group_names = [
        str(row.get("name") or "").strip()
        for row in schedulable_technicians(self.repo)
        if class_map.get(str(row.get("name") or "").strip(), v16.UNCLASSIFIED) == group
    ]
    group_names.sort(
        key=lambda item: (
            0 if item in manual else 1,
            manual.get(item, 0.0),
            planning_sorting.alpha_key(item),
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

    neighbor = group_names[target]
    current_order = manual.get(name)
    neighbor_order = manual.get(neighbor)

    if (
        current_order is not None
        and neighbor_order is not None
        and float(current_order) != float(neighbor_order)
    ):
        updates = {name: neighbor_order, neighbor: current_order}
    else:
        group_names[index], group_names[target] = group_names[target], group_names[index]
        updates = {
            resource_name: position * 10
            for position, resource_name in enumerate(group_names, start=1)
        }

    try:
        _write_order_column(self.repo, updates)
        self._after_write(f"{name} déplacé dans l'ordre manuel")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _install_resource_write_optimizations() -> None:
    if getattr(resource_management, "_runtime_resource_writes_installed", False):
        return

    original_update_profile = v16_refinements.update_resource_profile
    original_split_allocation = drop_handler_module._split_allocation

    def update_resource_profile_batched(
        repo: ExcelRepository,
        technician: str,
        resource_class: str | None,
        competencies: Any,
        note: str = "",
        order: Any = None,
    ) -> None:
        with repo.batch_update("update resource profile"):
            original_update_profile(
                repo,
                technician,
                resource_class,
                competencies,
                note,
                order,
            )

    def split_allocation_batched(
        self: ui_module.PlannerUI,
        allocation: dict[str, Any],
        target_technician: str,
        target_day: Any,
        hors_horaire: bool,
        *,
        bindings: Any,
    ) -> None:
        with self.repo.batch_update("split allocation"):
            original_split_allocation(
                self,
                allocation,
                target_technician,
                target_day,
                hors_horaire,
                bindings=bindings,
            )

    v16_refinements.update_resource_profile = update_resource_profile_batched
    resource_management._manual_order_dialog = _manual_order_dialog_fast
    sorting_compat.move_manual_resource = _move_manual_resource_fast
    ui_module.PlannerUI.move_resource_manual = _move_manual_resource_fast
    drop_handler_module._split_allocation = split_allocation_batched
    resource_management._runtime_resource_writes_installed = True


def install_runtime_performance_compat() -> None:
    if getattr(ExcelRepository, "_runtime_performance_installed", False):
        return

    _install_repository_batching()
    _install_availability_optimizations()
    _install_schema_ensure_optimizations()
    _install_resource_write_optimizations()

    ExcelRepository._runtime_performance_installed = True

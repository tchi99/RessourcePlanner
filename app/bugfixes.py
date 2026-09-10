from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Callable

from . import features
from . import ui as ui_module
from .domain.availability_rules import has_standard_schedule_in_window


def _format_excel_time(value: Any) -> str:
    """Convert Excel/COM time values to HH:MM.

    Excel often exposes a time-only cell as a fraction of a day (e.g. 0.333333
    for 08:00). xlwings may also return datetime/time objects or strings.
    """
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    if isinstance(value, dt_time):
        return value.strftime("%H:%M")

    if isinstance(value, (int, float)):
        minutes = int(round((float(value) % 1.0) * 24 * 60)) % (24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    text = str(value).strip()
    try:
        numeric = float(text.replace(",", "."))
    except ValueError:
        numeric = None
    if numeric is not None and 0 <= numeric < 1:
        minutes = int(round(numeric * 24 * 60)) % (24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    if len(text) >= 5 and text[2] == ":" and text[:2].isdigit() and text[3:5].isdigit():
        return text[:5]
    return text


def _has_active_standard_schedule(
    repo: Any,
    technician: str,
    start: date | None = None,
    end: date | None = None,
) -> bool:
    name = str(technician or "").strip()
    if not name:
        return False
    records = features.availability_records(repo)
    if start is not None:
        return has_standard_schedule_in_window(records, name, start, end or start)
    return any(
        str(row.get("Type") or "").strip() == "Horaire standard"
        and features._is_active(row.get("Actif"))
        and str(row.get("Technicien") or "").strip() == name
        for row in records
    )


def schedulable_technicians(
    repo: Any,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """Return employees whose standard schedule covers the requested display window."""
    return [
        tech
        for tech in repo.technicians()
        if _has_active_standard_schedule(repo, tech.get("name", ""), start, end)
    ]


def _run_with_schedulable_technicians(
    planner: ui_module.PlannerUI,
    callback: Callable[..., Any],
    *args: Any,
    start: date | None = None,
    end: date | None = None,
    **kwargs: Any,
) -> Any:
    """Temporarily filter repo.technicians while a legacy planning dialog is built."""
    repo = planner.repo
    original = repo.technicians
    filtered = schedulable_technicians(repo, start, end)
    repo.technicians = lambda: filtered
    try:
        return callback(*args, **kwargs)
    finally:
        repo.technicians = original


def install_bugfixes() -> None:
    if getattr(features, "_v12_bugfixes_installed", False):
        return

    original_records = features.availability_records

    def normalized_records(repo: Any) -> list[dict[str, Any]]:
        rows = original_records(repo)
        for row in rows:
            row["HeureDebut"] = _format_excel_time(row.get("HeureDebut"))
            row["HeureFin"] = _format_excel_time(row.get("HeureFin"))
        return rows

    features.availability_records = normalized_records

    original_availability_for_day = features.availability_for_day

    def availability_for_day(repo: Any, technician: str, day: Any) -> dict[str, Any]:
        target_day = day if isinstance(day, date) else None
        if target_day is not None and not _has_active_standard_schedule(
            repo, technician, target_day, target_day
        ):
            return {
                "available": False,
                "reason": "Aucun horaire standard pour cette date",
                "hours": "",
                "type": "Non planifiable",
            }
        if target_day is None and not _has_active_standard_schedule(repo, technician):
            return {
                "available": False,
                "reason": "Aucun horaire standard",
                "hours": "",
                "type": "Non planifiable",
            }
        return original_availability_for_day(repo, technician, day)

    features.availability_for_day = availability_for_day

    original_render_planning = ui_module.PlannerUI.render_planning
    original_effort_dialog = ui_module.PlannerUI.open_effort_dialog

    def render_planning(self: ui_module.PlannerUI) -> Any:
        start = self.current_week
        return _run_with_schedulable_technicians(
            self,
            lambda: original_render_planning(self),
            start=start,
            end=start + timedelta(days=6),
        )

    def open_effort_dialog(self: ui_module.PlannerUI, effort: dict[str, Any]) -> Any:
        return _run_with_schedulable_technicians(
            self, lambda: original_effort_dialog(self, effort)
        )

    ui_module.PlannerUI.render_planning = render_planning
    ui_module.PlannerUI.open_effort_dialog = open_effort_dialog

    features._v12_bugfixes_installed = True

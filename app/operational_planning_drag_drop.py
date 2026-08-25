from __future__ import annotations

import json
from datetime import date
from typing import Any


DROP_EVENT = "v17-planning-drop"


def make_draggable(element: Any, payload: str) -> Any:
    """Make a planning card draggable without depending on a V1.x module."""
    value = json.dumps(payload)
    element.props("draggable=true")
    element.classes("v17-draggable")
    element.on(
        "dragstart",
        js_handler=(
            "(event) => {"
            f"event.dataTransfer.setData('text/plain', {value});"
            "event.dataTransfer.effectAllowed = 'move';"
            "event.currentTarget.classList.add('v17-dragging');"
            "}"
        ),
    )
    element.on(
        "dragend",
        js_handler="(event) => event.currentTarget.classList.remove('v17-dragging')",
    )
    return element


def make_drop_zone(element: Any, technician: str, day: date | None = None) -> Any:
    """Make a planning resource/day cell accept the shared planning drop event."""
    tech_json = json.dumps(technician)
    day_json = json.dumps(day.isoformat() if day else "")
    element.classes("v17-drop-zone")
    element.on(
        "dragover",
        js_handler=(
            "(event) => { event.preventDefault(); "
            "event.dataTransfer.dropEffect = 'move'; "
            "event.currentTarget.classList.add('v17-drop-hover'); }"
        ),
    )
    element.on(
        "dragleave",
        js_handler="(event) => event.currentTarget.classList.remove('v17-drop-hover')",
    )
    element.on(
        "drop",
        js_handler=(
            "(event) => { event.preventDefault(); "
            "event.currentTarget.classList.remove('v17-drop-hover'); "
            f"emitEvent('{DROP_EVENT}', {{"
            "payload: event.dataTransfer.getData('text/plain'), "
            f"technician: {tech_json}, date: {day_json}"
            "}); }"
        ),
    )
    return element

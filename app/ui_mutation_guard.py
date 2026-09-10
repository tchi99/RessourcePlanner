from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


def set_actions_enabled(actions: Iterable[Any], enabled: bool) -> None:
    """Best-effort enable/disable without importing NiceGUI into the guard policy."""

    for action in actions:
        if action is None:
            continue
        setter = getattr(action, "set_enabled", None)
        if callable(setter):
            setter(enabled)
            continue
        method = getattr(action, "enable" if enabled else "disable", None)
        if callable(method):
            method()


@dataclass(slots=True)
class MutationGate:
    """Small V1 guard against duplicate NiceGUI mutation events.

    Browser double-clicks can enqueue two server events even when the first event closes
    a dialog. A successful dialog mutation therefore remains completed for that dialog
    instance. Failed validation/persistence can release the gate for an explicit retry.
    Controls passed to ``begin`` are disabled immediately as an additional browser-side
    signal; this module stays UI-framework neutral so it can be unit tested cheaply.
    """

    _state: str = "ready"

    @property
    def running(self) -> bool:
        return self._state == "running"

    @property
    def completed(self) -> bool:
        return self._state == "completed"

    def begin(self, actions: Iterable[Any] = ()) -> bool:
        """Acquire the mutation slot once and disable its visible actions."""

        if self._state != "ready":
            return False
        self._state = "running"
        set_actions_enabled(actions, False)
        return True

    def succeed(self) -> None:
        """Seal the gate after a successful one-shot dialog write."""

        if self._state == "running":
            self._state = "completed"

    def retry(self, actions: Iterable[Any] = ()) -> None:
        """Release a failed/invalid attempt and re-enable its controls."""

        if self._state == "running":
            self._state = "ready"
            set_actions_enabled(actions, True)

    def reset(self, actions: Iterable[Any] = ()) -> None:
        """Explicitly reopen a reusable action after a short success cooldown."""

        self._state = "ready"
        set_actions_enabled(actions, True)

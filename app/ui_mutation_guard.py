from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MutationGate:
    """One-dialog guard against duplicate NiceGUI mutation events.

    Browser double-clicks can enqueue two server events even when the first event closes
    the dialog. A successful mutation therefore keeps the gate permanently completed for
    that dialog instance. Validation or persistence failures may explicitly release it so
    the user can correct the form and retry.
    """

    _state: str = "ready"

    @property
    def running(self) -> bool:
        return self._state == "running"

    @property
    def completed(self) -> bool:
        return self._state == "completed"

    def begin(self) -> bool:
        """Acquire the mutation slot once; return False for duplicate events."""

        if self._state != "ready":
            return False
        self._state = "running"
        return True

    def succeed(self) -> None:
        """Seal the gate after a successful write for the lifetime of the dialog."""

        if self._state == "running":
            self._state = "completed"

    def retry(self) -> None:
        """Release a failed/invalid attempt so a corrected submission can run."""

        if self._state == "running":
            self._state = "ready"

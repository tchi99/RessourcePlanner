from __future__ import annotations

from datetime import date
import unittest

import app.operational_planning_cell_action as cell_action


class OperationalPlanningCellActionTests(unittest.TestCase):
    def tearDown(self) -> None:
        cell_action._registered_cell_shift_opener = None

    def test_registered_opener_receives_owner_resource_and_day(self) -> None:
        calls: list[tuple[object, str, date]] = []
        owner = object()
        day = date(2026, 8, 25)

        cell_action.register_operational_planning_cell_shift_opener(
            lambda target_owner, technician, target_day: calls.append(
                (target_owner, technician, target_day)
            )
        )
        cell_action.open_operational_planning_cell_shift(owner, "Mathieu", day)

        self.assertEqual(calls, [(owner, "Mathieu", day)])

    def test_invalid_or_missing_opener_fails_explicitly(self) -> None:
        with self.assertRaises(TypeError):
            cell_action.register_operational_planning_cell_shift_opener(None)  # type: ignore[arg-type]
        with self.assertRaises(RuntimeError):
            cell_action.open_operational_planning_cell_shift(
                object(), "Mathieu", date(2026, 8, 25)
            )


if __name__ == "__main__":
    unittest.main()

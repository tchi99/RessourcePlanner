from __future__ import annotations

from datetime import date
import unittest

from app.application import DemandReadModel, emergency_override_eligibility


class EmergencyPriorityAliasTests(unittest.TestCase):
    def test_react_urgente_spelling_is_eligible(self) -> None:
        demand = DemandReadModel(
            number="D-REACT",
            status="Soumise",
            priority="Urgente",
            desired_start=date(2026, 9, 16),
            desired_end=date(2026, 9, 16),
        )

        self.assertEqual(
            emergency_override_eligibility(demand, today=date(2026, 9, 16)),
            (True, None),
        )


if __name__ == "__main__":
    unittest.main()

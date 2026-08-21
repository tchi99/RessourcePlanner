from __future__ import annotations

import unittest

from app.domain.planning_snapshot import PlanningSnapshot


class PlanningSnapshotTests(unittest.TestCase):
    def test_capture_defensively_copies_source_rows(self) -> None:
        segments = [{"IDSegment": "S1", "HeuresPrevues": 8}]
        allocations = [{"IDAllocation": "A1", "Heures": 4}]

        snapshot = PlanningSnapshot.capture(
            segments=segments,
            demands=[{"NoDemande": "D1"}],
            allocations=allocations,
            availability=[{"ID": "AV1"}],
            technicians=[{"name": "R1"}],
        )

        segments[0]["HeuresPrevues"] = 99
        allocations.append({"IDAllocation": "A2", "Heures": 4})

        self.assertEqual(snapshot.segments[0]["HeuresPrevues"], 8)
        self.assertEqual(len(snapshot.allocations), 1)
        self.assertEqual(snapshot.allocations[0]["IDAllocation"], "A1")

    def test_capture_keeps_each_source_separate_and_ordered(self) -> None:
        snapshot = PlanningSnapshot.capture(
            segments=[{"IDSegment": "S1"}, {"IDSegment": "S2"}],
            demands=[{"NoDemande": "D1"}],
            allocations=[{"IDAllocation": "A1"}],
            availability=[{"ID": "AV1"}, {"ID": "AV2"}],
            technicians=[{"name": "R1"}, {"name": "R2"}],
        )

        self.assertEqual([row["IDSegment"] for row in snapshot.segments], ["S1", "S2"])
        self.assertEqual([row["name"] for row in snapshot.technicians], ["R1", "R2"])
        self.assertEqual(len(snapshot.demands), 1)
        self.assertEqual(len(snapshot.availability), 2)


if __name__ == "__main__":
    unittest.main()

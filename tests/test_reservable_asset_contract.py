import unittest
from datetime import date

from app.domain.reservable_assets import (
    AssetOccupation,
    CapacityOwner,
    LineKind,
    overlapping_asset_occupations,
)


class ReservableAssetContractTests(unittest.TestCase):
    def test_exclusive_day_overlap_includes_endpoints(self):
        first = AssetOccupation("first", "lift", date(2026, 9, 23), date(2026, 9, 25))
        second = AssetOccupation("second", "lift", date(2026, 9, 25), date(2026, 9, 26))
        self.assertEqual(overlapping_asset_occupations(second, [first]), ("first",))
        self.assertEqual(len(first.dates()), 3)

    def test_different_asset_or_same_allocation_is_not_conflict(self):
        first = AssetOccupation("first", "lift", date(2026, 9, 23), date(2026, 9, 23))
        other = AssetOccupation("other", "truck", date(2026, 9, 23), date(2026, 9, 23))
        self.assertEqual(overlapping_asset_occupations(first, [first, other]), ())
        self.assertNotEqual(CapacityOwner(LineKind.ASSET, "lift"), CapacityOwner(LineKind.WORKFORCE, "lift"))

    def test_invalid_window_rejected(self):
        with self.assertRaises(ValueError):
            AssetOccupation("a", "lift", date(2026, 9, 25), date(2026, 9, 23))

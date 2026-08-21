from __future__ import annotations

import unittest

from app.location_projection import (
    APPROVED_DEMAND_STATUS,
    approved_backfill_updates,
    location_for_new_segment,
    location_label,
    project_allocation_locations,
)


class LocationProjectionTests(unittest.TestCase):
    def test_approved_demand_can_seed_new_segment_location(self) -> None:
        result = location_for_new_segment(
            {"NoDemande": "REQ-1"},
            [],
            {
                "NoDemande": "REQ-1",
                "Statut": APPROVED_DEMAND_STATUS,
                "SiteClient": "Usine A",
                "Lieu": "Bâtiment 3",
            },
        )

        self.assertEqual(result, {"SiteClient": "Usine A", "Lieu": "Bâtiment 3"})

    def test_pending_demand_cannot_leak_new_location_into_segment(self) -> None:
        result = location_for_new_segment(
            {"NoDemande": "REQ-1"},
            [],
            {
                "NoDemande": "REQ-1",
                "Statut": "Soumise",
                "SiteClient": "Nouvelle usine en attente",
                "Lieu": "Nouveau bâtiment",
            },
        )

        self.assertEqual(result, {"SiteClient": "", "Lieu": ""})

    def test_existing_segment_snapshot_wins_while_request_is_pending(self) -> None:
        result = location_for_new_segment(
            {"NoDemande": "REQ-1"},
            [
                {
                    "IDSegment": "SEG-1",
                    "NoDemande": "REQ-1",
                    "SiteClient": "Usine approuvée",
                    "Lieu": "Salle électrique",
                }
            ],
            {
                "NoDemande": "REQ-1",
                "Statut": "Soumise",
                "SiteClient": "Usine modifiée",
                "Lieu": "Autre salle",
            },
        )

        self.assertEqual(
            result,
            {"SiteClient": "Usine approuvée", "Lieu": "Salle électrique"},
        )

    def test_backfill_only_uses_currently_approved_demand(self) -> None:
        segment = {"IDSegment": "SEG-1", "SiteClient": "", "Lieu": ""}
        approved = {
            "Statut": APPROVED_DEMAND_STATUS,
            "SiteClient": "Usine A",
            "Lieu": "Local 5",
        }
        pending = {
            "Statut": "Soumise",
            "SiteClient": "Usine B",
            "Lieu": "Local 9",
        }

        self.assertEqual(
            approved_backfill_updates(segment, approved),
            {"SiteClient": "Usine A", "Lieu": "Local 5"},
        )
        self.assertEqual(approved_backfill_updates(segment, pending), {})

    def test_backfill_does_not_replace_existing_segment_snapshot(self) -> None:
        result = approved_backfill_updates(
            {"SiteClient": "Site déjà projeté", "Lieu": ""},
            {
                "Statut": APPROVED_DEMAND_STATUS,
                "SiteClient": "Autre site",
                "Lieu": "Local 7",
            },
        )

        self.assertEqual(result, {"Lieu": "Local 7"})

    def test_allocation_location_is_projected_only_from_segment_snapshot(self) -> None:
        rows = project_allocation_locations(
            [
                {
                    "IDAllocation": "ALLOC-1",
                    "IDSegment": "SEG-1",
                    "SiteClient": "Valeur obsolète",
                    "Lieu": "Valeur obsolète",
                }
            ],
            [
                {
                    "IDSegment": "SEG-1",
                    "SiteClient": "Usine approuvée",
                    "Lieu": "Local 210",
                }
            ],
        )

        self.assertEqual(rows[0]["SiteClient"], "Usine approuvée")
        self.assertEqual(rows[0]["Lieu"], "Local 210")

    def test_unmatched_allocation_keeps_its_existing_location(self) -> None:
        rows = project_allocation_locations(
            [
                {
                    "IDAllocation": "ALLOC-ORPHAN",
                    "IDSegment": "SEG-MISSING",
                    "SiteClient": "Site conservé",
                    "Lieu": "Lieu conservé",
                }
            ],
            [],
        )

        self.assertEqual(rows[0]["SiteClient"], "Site conservé")
        self.assertEqual(rows[0]["Lieu"], "Lieu conservé")

    def test_location_label_avoids_duplicate_site_and_place(self) -> None:
        self.assertEqual(
            location_label({"SiteClient": "Usine A", "Lieu": "Usine A"}),
            "Usine A",
        )
        self.assertEqual(
            location_label({"SiteClient": "Usine A", "Lieu": "Local 12"}),
            "Usine A · Local 12",
        )


if __name__ == "__main__":
    unittest.main()

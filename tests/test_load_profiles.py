from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from app.domain.load_profiles import (
    LOAD_PROFILE_BACK_LOADED,
    LOAD_PROFILE_BELL,
    LOAD_PROFILE_FRONT_LOADED,
    LOAD_PROFILE_UNIFORM,
    load_profile_weights,
    normalize_load_profile,
    spread_profile_hours,
)
from app.domain.planning_engine import LockedAllocationInput, SegmentInput, build_allocation_plan
from app.infrastructure.sql import (
    Base,
    Project,
    SqlSegmentRepository,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


D1 = date(2026, 9, 14)
D2 = date(2026, 9, 15)
D3 = date(2026, 9, 16)
D4 = date(2026, 9, 17)
D5 = date(2026, 9, 18)
DAYS = (D1, D2, D3, D4, D5)


def automatic_hours(result):
    return {
        row.day: round(row.hours, 4)
        for row in result.allocations
        if not row.locked and row.counts_as_allocated
    }


class LoadProfilePolicyTests(unittest.TestCase):
    def test_profiles_normalize_to_stable_identifiers(self) -> None:
        self.assertEqual(normalize_load_profile(None), LOAD_PROFILE_UNIFORM)
        self.assertEqual(normalize_load_profile("Uniforme"), LOAD_PROFILE_UNIFORM)
        self.assertEqual(normalize_load_profile("Début"), LOAD_PROFILE_FRONT_LOADED)
        self.assertEqual(normalize_load_profile("Fin"), LOAD_PROFILE_BACK_LOADED)
        self.assertEqual(normalize_load_profile("Cloche"), LOAD_PROFILE_BELL)
        with self.assertRaisesRegex(ValueError, "profil de charge"):
            normalize_load_profile("random")

    def test_weight_shapes_are_deterministic(self) -> None:
        self.assertEqual(load_profile_weights(LOAD_PROFILE_UNIFORM, 5), (1.0, 1.0, 1.0, 1.0, 1.0))
        self.assertEqual(load_profile_weights(LOAD_PROFILE_FRONT_LOADED, 3), (3.0, 2.0, 1.0))
        self.assertEqual(load_profile_weights(LOAD_PROFILE_BACK_LOADED, 3), (1.0, 2.0, 3.0))
        self.assertEqual(load_profile_weights(LOAD_PROFILE_BELL, 5), (1.0, 2.0, 3.0, 2.0, 1.0))
        self.assertEqual(load_profile_weights(LOAD_PROFILE_BELL, 4), (1.0, 2.0, 2.0, 1.0))

    def test_weighted_spread_preserves_total_and_daily_capacity(self) -> None:
        capacity = ((D1, 8.0), (D2, 8.0), (D3, 8.0))
        self.assertEqual(
            spread_profile_hours(12, capacity, LOAD_PROFILE_FRONT_LOADED),
            {D1: 6.0, D2: 4.0, D3: 2.0},
        )
        self.assertEqual(
            spread_profile_hours(12, capacity, LOAD_PROFILE_BACK_LOADED),
            {D1: 2.0, D2: 4.0, D3: 6.0},
        )
        constrained = spread_profile_hours(
            12,
            ((D1, 2.0), (D2, 8.0), (D3, 8.0)),
            LOAD_PROFILE_FRONT_LOADED,
        )
        self.assertEqual(round(sum(constrained.values()), 4), 12.0)
        self.assertLessEqual(constrained[D1], 2.0)
        self.assertTrue(all(hours <= 8.0 for hours in constrained.values()))

    def test_uniform_profile_keeps_existing_engine_behavior(self) -> None:
        capacity = {("Alice", D1): 8.0, ("Alice", D2): 4.0, ("Alice", D3): 8.0}
        default = SegmentInput("S1", "Alice", D1, D3, 10)
        explicit = SegmentInput("S1", "Alice", D1, D3, 10, load_profile=LOAD_PROFILE_UNIFORM)
        default_plan = build_allocation_plan((default,), (), capacity)
        explicit_plan = build_allocation_plan((explicit,), (), capacity)
        self.assertEqual(default_plan.allocations, explicit_plan.allocations)

    def test_profile_and_active_day_target_choose_the_expected_region(self) -> None:
        capacity = {("Alice", day): 8.0 for day in DAYS}
        cases = (
            (LOAD_PROFILE_FRONT_LOADED, {D1, D2, D3}),
            (LOAD_PROFILE_BACK_LOADED, {D3, D4, D5}),
            (LOAD_PROFILE_BELL, {D2, D3, D4}),
        )
        for profile, expected_days in cases:
            with self.subTest(profile=profile):
                segment = SegmentInput(
                    "S1",
                    "Alice",
                    D1,
                    D5,
                    12,
                    desired_active_days=3,
                    load_profile=profile,
                )
                plan = build_allocation_plan((segment,), (), capacity)
                self.assertEqual(set(automatic_hours(plan)), expected_days)
                self.assertEqual(round(plan.allocated_hours, 2), 12.0)
                self.assertEqual(plan.active_day_diagnostics, ())

    def test_locked_days_are_preserved_and_consume_active_day_target_first(self) -> None:
        capacity = {("Alice", day): 8.0 for day in DAYS}
        segment = SegmentInput(
            "S1",
            "Alice",
            D1,
            D5,
            24,
            desired_active_days=3,
            load_profile=LOAD_PROFILE_BACK_LOADED,
        )
        locked = (LockedAllocationInput("S1", "Alice", D1, 8),)
        plan = build_allocation_plan((segment,), locked, capacity)
        locked_row = next(row for row in plan.allocations if row.locked)
        self.assertEqual((locked_row.day, locked_row.hours), (D1, 8.0))
        self.assertEqual(set(automatic_hours(plan)), {D4, D5})
        self.assertEqual({row.day for row in plan.allocations if row.counts_as_allocated}, {D1, D4, D5})
        self.assertEqual(round(plan.allocated_hours, 2), 24.0)

    def test_capacity_shortage_wins_over_profile_without_silent_hours(self) -> None:
        segment = SegmentInput(
            "S1",
            "Alice",
            D1,
            D3,
            30,
            load_profile=LOAD_PROFILE_FRONT_LOADED,
        )
        capacity = {("Alice", D1): 8.0, ("Alice", D2): 8.0, ("Alice", D3): 8.0}
        plan = build_allocation_plan((segment,), (), capacity)
        self.assertEqual(round(plan.allocated_hours, 2), 24.0)
        self.assertEqual(round(plan.unallocated_hours, 2), 6.0)
        self.assertTrue(all(row.hours <= 8.0 for row in plan.allocations if row.counts_as_allocated))


class LoadProfileSqlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with transactional_session(self.factory) as session:
            session.add(Project(id="P1", number="P-14", name="Projet profils"))
            session.add(
                WorkforceRequest(
                    id="D1",
                    legacy_demand_number="DEM-14",
                    project_id="P1",
                    desired_start=D1,
                    desired_end=D5,
                    estimated_hours=Decimal("20"),
                    resource_count=1,
                    status="En planification",
                )
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_segment_defaults_to_uniform_and_can_be_changed(self) -> None:
        with transactional_session(self.factory) as session:
            repository = SqlSegmentRepository(session)
            reference = repository.create(
                {
                    "NoDemande": "DEM-14",
                    "NumeroProjet": "P-14",
                    "DateDebut": D1,
                    "DateFin": D5,
                    "HeuresPrevues": 20,
                    "TypePlanification": "Flexible",
                }
            )
            created = repository.get(reference)
            self.assertIsNotNone(created)
            self.assertEqual(created.load_profile, LOAD_PROFILE_UNIFORM)

            repository.update(reference, {"ProfilCharge": LOAD_PROFILE_BELL})
            updated = repository.get(reference)
            self.assertIsNotNone(updated)
            self.assertEqual(updated.load_profile, LOAD_PROFILE_BELL)

    def test_invalid_profile_is_rejected_at_repository_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "profil de charge"):
            with transactional_session(self.factory) as session:
                SqlSegmentRepository(session).create(
                    {
                        "NoDemande": "DEM-14",
                        "NumeroProjet": "P-14",
                        "DateDebut": D1,
                        "DateFin": D5,
                        "HeuresPrevues": 20,
                        "ProfilCharge": "zigzag",
                    }
                )


if __name__ == "__main__":
    unittest.main()

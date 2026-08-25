from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from app.operational_planning_header_filters import (
    HeaderFilterBindings,
    resolve_planning_filter_state,
)
from app.operational_planning_resource_groups import (
    ResourceGroupingBindings,
    group_operational_planning_resources,
    ordered_resource_group_names,
    resource_group_totals,
)


class OperationalPlanningHeaderFilterTests(unittest.TestCase):
    def _bindings(self, stored: dict[str, object]) -> HeaderFilterBindings:
        return HeaderFilterBindings(
            all_classes="Toutes les classes",
            resource_classes=("Programmation", "Installation"),
            unclassified="Non classé",
            all_resources="Toutes les ressources",
            all_projects="Tous les projets",
            all_confirmations="Toutes",
            filter_value=lambda _owner, name, default: stored.get(name, default),
            set_filter=lambda *_args: None,
            project_labels=lambda _repo: {
                "P1": "P1 — Projet un",
                "P3": "P3 — Projet trois",
            },
            open_manual_allocation=lambda _owner: None,
            recalculate=lambda _owner: None,
        )

    def test_resolve_state_preserves_filters_and_builds_sorted_project_options(self) -> None:
        owner = SimpleNamespace(repo=object())
        stored = {
            "planning_class_filter": "Programmation",
            "planning_resource_filter": "Alice",
            "planning_project_filter": "P2",
            "planning_confirmation_filter": "Tentative",
            "planning_only_available": True,
        }
        state = resolve_planning_filter_state(
            owner,
            [{"NumeroProjet": "P2"}, {"NumeroProjet": "P1"}],
            [{"NumeroProjet": "P3"}, {"NumeroProjet": "P2"}],
            [{"NumeroProjet": "P1"}],
            bindings=self._bindings(stored),
        )

        self.assertEqual(state.class_filter, "Programmation")
        self.assertEqual(state.resource_filter, "Alice")
        self.assertEqual(state.project_filter, "P2")
        self.assertEqual(state.confirmation_filter, "Tentative")
        self.assertTrue(state.only_available)
        self.assertEqual(
            list(state.project_options.items()),
            [
                ("Tous les projets", "Tous les projets"),
                ("P1", "P1 — Projet un"),
                ("P2", "P2"),
                ("P3", "P3 — Projet trois"),
            ],
        )

    def test_resolve_state_uses_defaults_when_no_filter_is_saved(self) -> None:
        owner = SimpleNamespace(repo=object())
        state = resolve_planning_filter_state(
            owner,
            [],
            [],
            [],
            bindings=self._bindings({}),
        )

        self.assertEqual(state.class_filter, "Toutes les classes")
        self.assertEqual(state.resource_filter, "Toutes les ressources")
        self.assertEqual(state.project_filter, "Tous les projets")
        self.assertEqual(state.confirmation_filter, "Toutes")
        self.assertFalse(state.only_available)
        self.assertEqual(state.project_options, {"Tous les projets": "Tous les projets"})


class OperationalPlanningResourceGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        order = {"Installation": 0, "Programmation": 1, "Non classé": 2}
        self.bindings = ResourceGroupingBindings(
            all_classes="Toutes les classes",
            all_resources="Toutes les ressources",
            unclassified="Non classé",
            resource_group_order=lambda name: order.get(name, 99),
        )
        self.techs = [
            {"name": "Alice"},
            {"name": "Bob"},
            {"name": "Chloé"},
            {"name": "David"},
        ]
        self.class_map = {
            "Alice": "Programmation",
            "Bob": "Programmation",
            "Chloé": "Installation",
        }
        self.week_stats = {
            "Alice": {"prudent_free": 4.0, "capacity": 40.0},
            "Bob": {"prudent_free": 8.0, "capacity": 40.0},
            "Chloé": {"prudent_free": 0.0, "capacity": 32.0},
            "David": {"prudent_free": 2.0, "capacity": 24.0},
        }

    def test_groups_resources_and_sorts_each_group_by_free_capacity(self) -> None:
        grouped = group_operational_planning_resources(
            self.techs,
            self.class_map,
            self.week_stats,
            "Toutes les classes",
            "Toutes les ressources",
            False,
            bindings=self.bindings,
        )

        self.assertEqual(
            [tech["name"] for tech in grouped["Programmation"]],
            ["Bob", "Alice"],
        )
        self.assertEqual([tech["name"] for tech in grouped["Installation"]], ["Chloé"])
        self.assertEqual([tech["name"] for tech in grouped["Non classé"]], ["David"])
        self.assertEqual(
            ordered_resource_group_names(grouped, bindings=self.bindings),
            ["Installation", "Programmation", "Non classé"],
        )

    def test_filters_by_class_resource_and_positive_capacity(self) -> None:
        grouped = group_operational_planning_resources(
            self.techs,
            self.class_map,
            self.week_stats,
            "Programmation",
            "Bob",
            True,
            bindings=self.bindings,
        )
        self.assertEqual(list(grouped), ["Programmation"])
        self.assertEqual([tech["name"] for tech in grouped["Programmation"]], ["Bob"])

        no_capacity = group_operational_planning_resources(
            self.techs,
            self.class_map,
            self.week_stats,
            "Installation",
            "Toutes les ressources",
            True,
            bindings=self.bindings,
        )
        self.assertEqual(no_capacity, {})

    def test_group_totals_match_week_stats(self) -> None:
        total_free, total_capacity = resource_group_totals(
            [{"name": "Bob"}, {"name": "Alice"}],
            self.week_stats,
        )
        self.assertEqual(total_free, 12.0)
        self.assertEqual(total_capacity, 80.0)


class OperationalPlanningExtractionGuards(unittest.TestCase):
    def test_non_versioned_modules_do_not_import_v1_layers(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        for filename in (
            "operational_planning_header_filters.py",
            "operational_planning_resource_groups.py",
        ):
            source = (app_dir / filename).read_text(encoding="utf-8")
            for version in ("v13", "v14", "v15", "v16", "v17", "v18"):
                self.assertNotIn(f"from . import {version}", source, filename)
                self.assertNotIn(f"from .{version}", source, filename)

    def test_v17_delegates_filters_and_grouping(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "v17.py"
        ).read_text(encoding="utf-8")

        self.assertIn("resolve_planning_filter_state(", source)
        self.assertIn("render_operational_planning_header_filters(", source)
        self.assertIn("group_operational_planning_resources(", source)
        self.assertIn("ordered_resource_group_names(", source)
        self.assertNotIn('"planning_class_filter"', source)
        self.assertNotIn("filtered_techs", source)
        self.assertNotIn("grouped.setdefault", source)
        self.assertNotIn("ui.select(", source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from app.operational_planning_sorting import (
    MANUAL_ORDER_EVENT,
    SORT_ALPHA_ASC,
    SORT_AVAIL_ASC,
    SORT_MANUAL,
    alpha_key,
    manual_order_script,
    rank_weekly_stats,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningSortingTests(unittest.TestCase):
    def _owner(self, mode: str | None = None):
        owner = SimpleNamespace(repo=object(), render_content=SimpleNamespace(refresh=lambda: None))
        if mode is not None:
            owner.planning_resource_sort = mode
        return owner

    def _stats(self, repo, week):
        return {
            "Émile": {"prudent_free": 2.0, "capacity": 40.0},
            "Alice": {"prudent_free": 8.0, "capacity": 40.0},
            "Bob": {"prudent_free": 4.0, "capacity": 40.0},
        }

    def test_alpha_key_is_accent_and_case_insensitive(self) -> None:
        self.assertEqual(alpha_key("Émile"), alpha_key("emile"))
        self.assertEqual(alpha_key("ÀLEX"), alpha_key("alex"))

    def test_default_and_availability_ascending_ranks_preserve_displayed_hours(self) -> None:
        owner = self._owner()
        ranked = rank_weekly_stats(
            owner,
            self._stats,
            owner.repo,
            object(),
            order_map=lambda repo: {},
        )

        self.assertEqual(float(ranked["Alice"]["prudent_free"]), 8.0)
        self.assertEqual(-ranked["Alice"]["prudent_free"], 0)
        self.assertEqual(-ranked["Bob"]["prudent_free"], 1)
        self.assertEqual(-ranked["Émile"]["prudent_free"], 2)

        owner.planning_resource_sort = SORT_AVAIL_ASC
        ranked = rank_weekly_stats(
            owner,
            self._stats,
            owner.repo,
            object(),
            order_map=lambda repo: {},
        )
        self.assertEqual(-ranked["Émile"]["prudent_free"], 0)
        self.assertEqual(-ranked["Bob"]["prudent_free"], 1)
        self.assertEqual(-ranked["Alice"]["prudent_free"], 2)

    def test_alpha_and_manual_modes_are_deterministic(self) -> None:
        owner = self._owner(SORT_ALPHA_ASC)
        ranked = rank_weekly_stats(
            owner,
            self._stats,
            owner.repo,
            object(),
            order_map=lambda repo: {},
        )
        self.assertEqual(-ranked["Alice"]["prudent_free"], 0)
        self.assertEqual(-ranked["Bob"]["prudent_free"], 1)
        self.assertEqual(-ranked["Émile"]["prudent_free"], 2)

        owner.planning_resource_sort = SORT_MANUAL
        ranked = rank_weekly_stats(
            owner,
            self._stats,
            owner.repo,
            object(),
            order_map=lambda repo: {"Émile": 20.0, "Bob": 10.0},
        )
        self.assertEqual(-ranked["Bob"]["prudent_free"], 0)
        self.assertEqual(-ranked["Émile"]["prudent_free"], 1)
        self.assertEqual(-ranked["Alice"]["prudent_free"], 2)

    def test_manual_order_script_preserves_browser_contract(self) -> None:
        owner = self._owner(SORT_MANUAL)
        script = manual_order_script(owner, ["Alice", "Jean Charles"])

        self.assertIn(MANUAL_ORDER_EVENT, script)
        self.assertIn("v17-manual-order-controls", script)
        self.assertIn("Jean Charles", script)
        self.assertIn("Monter cette ressource", script)
        self.assertIn("Descendre cette ressource", script)

    def test_stable_sort_module_has_no_versioned_imports(self) -> None:
        source = (APP / "operational_planning_sorting.py").read_text(encoding="utf-8")
        for version in ("v13", "v14", "v15", "v16", "v17", "v18"):
            self.assertNotIn(f"from . import {version}", source)
            self.assertNotIn(f"from .{version}", source)


if __name__ == "__main__":
    unittest.main()

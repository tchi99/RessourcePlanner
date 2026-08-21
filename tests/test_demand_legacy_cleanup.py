from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from app.demand_legacy_cleanup import (
    _approve_demand_record_only,
    install_demand_legacy_cleanup,
)
from app.runtime_composition import composition_manifest


class DemandLegacyCleanupTests(unittest.TestCase):
    def test_record_only_fallback_has_no_sync_or_rebuild_side_effect(self) -> None:
        calls: list[tuple[object, ...]] = []

        class Repo:
            current_user = "coordinator"

            def update_demand(
                self,
                number: str,
                updates: dict[str, object],
                *,
                action: str,
                comment: str,
            ) -> None:
                calls.append((number, updates, action, comment))

        _approve_demand_record_only(Repo(), "DMO-1", "ok")

        self.assertEqual(len(calls), 1)
        number, updates, action, comment = calls[0]
        self.assertEqual(number, "DMO-1")
        self.assertEqual(action, "Approbation")
        self.assertEqual(comment, "ok")
        self.assertEqual(updates["Statut"], "En planification")
        self.assertEqual(updates["ApprouvePar"], "coordinator")
        self.assertEqual(updates["CommentaireApprobation"], "ok")

    def test_cleanup_replaces_stacked_legacy_method_idempotently(self) -> None:
        class FakeExcelRepository:
            def approve_demand(self, number: str, comment: str = "") -> None:
                raise AssertionError("legacy wrapper must be replaced")

        fake_module = ModuleType("app.excel_repository")
        fake_module.ExcelRepository = FakeExcelRepository  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"app.excel_repository": fake_module}):
            install_demand_legacy_cleanup()
            first = FakeExcelRepository.approve_demand
            install_demand_legacy_cleanup()
            second = FakeExcelRepository.approve_demand

        self.assertIs(first, _approve_demand_record_only)
        self.assertIs(second, _approve_demand_record_only)
        self.assertTrue(FakeExcelRepository._demand_legacy_cleanup_installed)

    def test_cleanup_runs_after_legacy_wrappers_before_application_ui(self) -> None:
        names = [step.name for step in composition_manifest()]
        self.assertLess(
            names.index("v18_workflow_fixes"),
            names.index("demand_legacy_cleanup"),
        )
        self.assertLess(
            names.index("demand_legacy_cleanup"),
            names.index("planning_service_ui"),
        )

    def test_v18_no_longer_installs_approval_batching_wrapper(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "v18_workflow_fixes.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("_install_approval_batching", source)
        self.assertNotIn("ExcelRepository.approve_demand", source)
        self.assertNotIn("nullcontext", source)


if __name__ == "__main__":
    unittest.main()

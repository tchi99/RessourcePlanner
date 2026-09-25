from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.application.errors import ApplicationConflictError
from app.application.resource_classes import (
    RESOLUTION_CLASS,
    RESOLUTION_EXCLUDED,
    RESOLUTION_UNCLASSIFIED,
    ResourceClassConfigurationService,
)
from app.infrastructure.sql import (
    ApprovalScope,
    Base,
    Project,
    ProjectTaskClassOverride,
    RequestLine,
    ResourceClassConfig,
    ResourceRequirement,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
)
from app.infrastructure.sql.resource_class_repository import (
    SqlResourceClassRepository,
)


class ResourceClassConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        self.session = self.factory()
        self.session.add_all(
            [
                Project(id="project-1", number="P-1", name="Projet 1"),
                Project(id="project-2", number="P-2", name="Projet 2"),
            ]
        )
        self.session.flush()
        self.service = ResourceClassConfigurationService(
            SqlResourceClassRepository(self.session)
        )
        self._create_baseline()

    def tearDown(self) -> None:
        self.session.rollback()
        self.session.close()
        self.engine.dispose()

    def _create_baseline(self) -> None:
        for code, label, cost in (
            (
                "INSTALLATEUR_ELECTRIQUE",
                "Installateur électrique",
                Decimal("100.00"),
            ),
            ("PROGRAMMEUR", "Programmeur", Decimal("125.00")),
            (
                "INSTALLATEUR_AUTOMATISATION",
                "Installateur automatisation",
                Decimal("110.00"),
            ),
        ):
            self.service.create_resource_class(
                code=code,
                label=label,
                average_hourly_cost_cad=cost,
                active=True,
            )
        for task_code, class_code in (
            ("117", "INSTALLATEUR_ELECTRIQUE"),
            ("216", "PROGRAMMEUR"),
            ("217", "INSTALLATEUR_AUTOMATISATION"),
        ):
            self.service.create_task_standard(
                task_code=task_code,
                resource_class_code=class_code,
                active=True,
            )

    def test_expected_global_standards_resolve_without_override(self) -> None:
        expected = {
            "117": "INSTALLATEUR_ELECTRIQUE",
            "216": "PROGRAMMEUR",
            "217": "INSTALLATEUR_AUTOMATISATION",
        }
        for task_code, class_code in expected.items():
            with self.subTest(task_code=task_code):
                resolution = self.service.resolve("project-1", task_code)
                self.assertEqual(resolution.status, RESOLUTION_CLASS)
                self.assertEqual(
                    resolution.resource_class_code,
                    class_code,
                )
                self.assertEqual(resolution.source, "STANDARD")
                self.assertEqual(resolution.diagnostics, ())

    def test_project_override_exclude_and_return_to_standard(self) -> None:
        created = self.service.set_project_override(
            "project-1",
            "216",
            resource_class_code="INSTALLATEUR_AUTOMATISATION",
        )
        overridden = self.service.resolve("project-1", "216")
        untouched = self.service.resolve("project-2", "216")
        self.assertEqual(
            overridden.resource_class_code,
            "INSTALLATEUR_AUTOMATISATION",
        )
        self.assertEqual(overridden.source, "PROJECT_OVERRIDE")
        self.assertEqual(untouched.resource_class_code, "PROGRAMMEUR")

        excluded = self.service.set_project_override(
            "project-1",
            "216",
            excluded=True,
            expected_version=created.version,
        )
        excluded_resolution = self.service.resolve(
            "project-1",
            "216",
        )
        self.assertTrue(excluded.excluded)
        self.assertEqual(
            excluded_resolution.status,
            RESOLUTION_EXCLUDED,
        )
        self.assertIn(
            "task_excluded",
            excluded_resolution.diagnostics,
        )

        restored = self.service.remove_project_override(
            "project-1",
            "216",
            expected_version=excluded.version,
        )
        self.assertEqual(restored.status, RESOLUTION_CLASS)
        self.assertEqual(restored.resource_class_code, "PROGRAMMEUR")
        self.assertEqual(restored.source, "STANDARD")

    def test_missing_standard_is_unclassified(self) -> None:
        resolution = self.service.resolve("project-1", "999")
        self.assertEqual(resolution.status, RESOLUTION_UNCLASSIFIED)
        self.assertIn(
            "task_standard_missing",
            resolution.diagnostics,
        )

    def test_inactive_class_is_explicit_diagnostic(self) -> None:
        row = next(
            item
            for item in self.service.list_resource_classes()
            if item.code == "PROGRAMMEUR"
        )
        self.service.update_resource_class(
            "PROGRAMMEUR",
            expected_version=row.version,
            active=False,
        )
        resolution = self.service.resolve("project-1", "216")
        self.assertEqual(resolution.status, RESOLUTION_UNCLASSIFIED)
        self.assertEqual(
            resolution.configured_resource_class_code,
            "PROGRAMMEUR",
        )
        self.assertIn(
            "standard_resource_class_inactive",
            resolution.diagnostics,
        )

    def test_missing_and_zero_cost_never_invent_hours(self) -> None:
        self.session.execute(
            update(ResourceClassConfig)
            .where(ResourceClassConfig.code == "PROGRAMMEUR")
            .values(average_hourly_cost_cad=None)
        )
        self.session.flush()
        missing = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("1000.00"),
        )
        self.assertIsNone(missing.budget_hours)
        self.assertIsNone(missing.average_hourly_cost_cad)
        self.assertIn(
            "resource_class_cost_missing",
            missing.diagnostics,
        )

        self.session.execute(
            update(ResourceClassConfig)
            .where(ResourceClassConfig.code == "PROGRAMMEUR")
            .values(average_hourly_cost_cad=Decimal("0"))
        )
        self.session.flush()
        zero = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("1000.00"),
        )
        self.assertIsNone(zero.budget_hours)
        self.assertEqual(
            zero.average_hourly_cost_cad,
            Decimal("0"),
        )
        self.assertIn("resource_class_cost_zero", zero.diagnostics)

    def test_decimal_projection_preserves_zero_and_negative_budget(self) -> None:
        projection = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("1000.00"),
        )
        self.assertEqual(
            projection.budget_hours,
            Decimal("1000.00") / Decimal("125.0000"),
        )
        self.assertEqual(
            projection.budget_amount_cad,
            Decimal("1000.00"),
        )
        self.assertEqual(
            projection.average_hourly_cost_cad,
            Decimal("125.0000"),
        )

        zero = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("0"),
        )
        self.assertEqual(zero.budget_hours, Decimal("0"))
        self.assertIn("budget_amount_zero", zero.diagnostics)

        negative = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("-250.00"),
        )
        self.assertEqual(
            negative.budget_hours,
            Decimal("-2"),
        )
        self.assertIn(
            "budget_amount_negative",
            negative.diagnostics,
        )

    def test_cost_change_changes_projection_without_rewriting_plan(self) -> None:
        self.session.add(
            WorkforceRequest(
                id="request-1",
                legacy_demand_number="DMO-1",
                project_id="project-1",
                status="En planification",
                line_mode=True,
            )
        )
        self.session.flush()
        self.session.add(
            RequestLine(
                id="line-1",
                workforce_request_id="request-1",
                position=0,
                required_resource_class="PROGRAMMEUR",
                estimated_hours=Decimal("12.00"),
                active=True,
            )
        )
        self.session.flush()
        self.session.add(
            ResourceRequirement(
                id="requirement-1",
                project_id="project-1",
                workforce_request_id="request-1",
                source_request_line_id="line-1",
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 1),
                planned_hours=Decimal("12.00"),
                required_resource_class="PROGRAMMEUR",
            )
        )
        self.session.flush()

        before = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("1000.00"),
        )
        resource_class = next(
            item
            for item in self.service.list_resource_classes()
            if item.code == "PROGRAMMEUR"
        )
        self.service.update_resource_class(
            "PROGRAMMEUR",
            expected_version=resource_class.version,
            average_hourly_cost_cad=Decimal("100.00"),
            average_hourly_cost_supplied=True,
        )
        after = self.service.project_budget_hours(
            "project-1",
            "216",
            Decimal("1000.00"),
        )

        self.assertNotEqual(before.budget_hours, after.budget_hours)
        self.assertEqual(after.budget_hours, Decimal("10"))
        line = self.session.get(RequestLine, "line-1")
        requirement = self.session.get(
            ResourceRequirement,
            "requirement-1",
        )
        self.assertEqual(line.estimated_hours, Decimal("12.00"))
        self.assertEqual(
            line.required_resource_class,
            "PROGRAMMEUR",
        )
        self.assertEqual(
            requirement.planned_hours,
            Decimal("12.00"),
        )
        self.assertEqual(
            requirement.required_resource_class,
            "PROGRAMMEUR",
        )

    def test_approval_scope_is_separate_from_workforce_class(self) -> None:
        self.session.add(
            ApprovalScope(
                id="approval-scope-1",
                code="PROGRAMMEUR",
                label="Même code volontairement",
                active=False,
                version=1,
            )
        )
        self.session.flush()

        resolution = self.service.resolve("project-1", "216")
        self.assertEqual(resolution.status, RESOLUTION_CLASS)
        self.assertEqual(
            resolution.resource_class_code,
            "PROGRAMMEUR",
        )
        self.assertNotIn(
            "approval",
            " ".join(resolution.diagnostics).casefold(),
        )

    def test_version_conflict_is_fail_closed(self) -> None:
        row = next(
            item
            for item in self.service.list_resource_classes()
            if item.code == "PROGRAMMEUR"
        )
        updated = self.service.update_resource_class(
            "PROGRAMMEUR",
            expected_version=row.version,
            label="Programmeur automation",
        )
        self.assertEqual(updated.version, row.version + 1)
        with self.assertRaises(ApplicationConflictError) as ctx:
            self.service.update_resource_class(
                "PROGRAMMEUR",
                expected_version=row.version,
                label="Stale",
            )
        self.assertEqual(
            ctx.exception.code,
            "resource_class_version_conflict",
        )

    def test_project_task_override_composite_key_is_unique(self) -> None:
        session = self.factory()
        try:
            session.add_all(
                [
                    ProjectTaskClassOverride(
                        project_id="project-1",
                        task_code="216",
                        resource_class_code="PROGRAMMEUR",
                        excluded=False,
                        version=1,
                    ),
                    ProjectTaskClassOverride(
                        project_id="project-1",
                        task_code="216",
                        resource_class_code=(
                            "INSTALLATEUR_AUTOMATISATION"
                        ),
                        excluded=False,
                        version=1,
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                session.flush()
        finally:
            session.rollback()
            session.close()


if __name__ == "__main__":
    unittest.main()

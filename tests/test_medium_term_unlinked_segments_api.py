from __future__ import annotations

from functools import partial

from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import (
    Base,
    Project,
    ResourceRequirement,
    WorkforceRequest,
    WorkPackage,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class MediumTermUnlinkedSegmentsApiTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "medium-term-unlinked.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)

        with factory.begin() as session:
            project = Project(
                id="P-274",
                number="P-274",
                name="Projet moyen terme",
                project_manager_name="CP Test",
                status="active",
            )
            session.add(project)
            package = WorkPackage(
                id="WP-274",
                project_id=project.id,
                code="WP-A",
                name="Lot principal",
                legacy_effort_id="EFF-274",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 12, 31),
                planned_hours=Decimal("120"),
                status="planned",
            )
            session.add(package)

            linked = WorkforceRequest(
                id="WR-LINKED",
                legacy_demand_number="DMO-274-LINKED",
                project_id=project.id,
                work_package_id=package.id,
                desired_start=date(2026, 9, 21),
                desired_end=date(2026, 9, 25),
                estimated_hours=Decimal("8"),
                status="En planification",
            )
            unlinked = WorkforceRequest(
                id="WR-UNLINKED",
                legacy_demand_number="DMO-274-UNLINKED",
                project_id=project.id,
                work_package_id=None,
                erp_task_code="310",
                erp_task_label="Programmation",
                desired_start=date(2026, 9, 21),
                desired_end=date(2026, 9, 25),
                estimated_hours=Decimal("16"),
                status="En planification",
            )
            session.add_all([linked, unlinked])
            session.flush()

            session.add_all(
                [
                    ResourceRequirement(
                        id="REQ-LINKED",
                        legacy_segment_id="SEG-274-LINKED",
                        project_id=project.id,
                        workforce_request_id=linked.id,
                        start_date=date(2026, 9, 21),
                        end_date=date(2026, 9, 25),
                        planned_hours=Decimal("8"),
                        status="Planifié",
                        origin="REQUEST",
                    ),
                    ResourceRequirement(
                        id="REQ-UNLINKED",
                        legacy_segment_id="SEG-274-UNLINKED",
                        project_id=project.id,
                        workforce_request_id=unlinked.id,
                        start_date=date(2026, 9, 21),
                        end_date=date(2026, 9, 25),
                        planned_hours=Decimal("16"),
                        status="À assigner",
                        origin="REQUEST",
                        description="Besoin approuvé non classé",
                    ),
                    ResourceRequirement(
                        id="REQ-ADHOC",
                        legacy_segment_id="SEG-274-ADHOC",
                        project_id=project.id,
                        workforce_request_id=None,
                        start_date=date(2026, 9, 22),
                        end_date=date(2026, 9, 22),
                        planned_hours=Decimal("4"),
                        status="Planifié",
                        origin="QUICK_SHIFT",
                        description="Intervention ad hoc",
                    ),
                    ResourceRequirement(
                        id="REQ-ADHOC-LINKED",
                        legacy_segment_id="SEG-274-ADHOC-LINKED",
                        project_id=project.id,
                        workforce_request_id=None,
                        start_date=date(2026, 9, 22),
                        end_date=date(2026, 9, 22),
                        planned_hours=Decimal("2"),
                        status="Planifié",
                        origin="AD_HOC",
                        source_effort_id="EFF-274",
                    ),
                    ResourceRequirement(
                        id="REQ-BROKEN",
                        legacy_segment_id="SEG-274-BROKEN",
                        project_id=project.id,
                        workforce_request_id=None,
                        start_date=date(2026, 9, 23),
                        end_date=date(2026, 9, 23),
                        planned_hours=Decimal("3"),
                        status="Planifié",
                        origin="AD_HOC",
                        source_effort_id="EFF-MISSING",
                    ),
                    ResourceRequirement(
                        id="REQ-OUTSIDE",
                        legacy_segment_id="SEG-274-OUTSIDE",
                        project_id=project.id,
                        workforce_request_id=None,
                        start_date=date(2027, 1, 4),
                        end_date=date(2027, 1, 4),
                        planned_hours=Decimal("4"),
                        status="Planifié",
                        origin="QUICK_SHIFT",
                    ),
                ]
            )

        engine.dispose()
        return url

    def test_projection_distinguishes_anomaly_and_legitimate_ad_hoc(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/medium-term/unlinked-segments",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                )

            self.assertEqual(response.status_code, 200, response.text)
            rows = {row["segment_id"]: row for row in response.json()}

            self.assertEqual(
                set(rows),
                {"SEG-274-UNLINKED", "SEG-274-ADHOC", "SEG-274-BROKEN"},
            )
            request_row = rows["SEG-274-UNLINKED"]
            self.assertEqual(request_row["classification"], "REQUEST_UNLINKED")
            self.assertTrue(request_row["anomaly"])
            self.assertEqual(request_row["link_target"], "DEMAND")
            self.assertTrue(request_row["reapproval_on_link"])
            self.assertEqual(request_row["task_code"], "310")

            ad_hoc = rows["SEG-274-ADHOC"]
            self.assertEqual(ad_hoc["classification"], "AD_HOC_ALLOWED")
            self.assertFalse(ad_hoc["anomaly"])
            self.assertEqual(ad_hoc["link_target"], "SEGMENT")

            broken = rows["SEG-274-BROKEN"]
            self.assertEqual(broken["classification"], "BROKEN_REFERENCE")
            self.assertTrue(broken["anomaly"])
            self.assertEqual(broken["current_work_package_ref"], "EFF-MISSING")

    def test_existing_commands_can_explicitly_attach_request_and_ad_hoc(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                demand_link = client.patch(
                    "/api/v1/demands/DMO-274-UNLINKED",
                    json={
                        "work_package_ref": "EFF-274",
                        "comment": "Rattachement moyen terme",
                    },
                )
                self.assertEqual(demand_link.status_code, 200, demand_link.text)
                self.assertTrue(demand_link.json()["reapproval_required"])

                segment_link = client.patch(
                    "/api/v1/segments/SEG-274-ADHOC",
                    json={"source_effort_id": "EFF-274"},
                )
                self.assertEqual(segment_link.status_code, 200, segment_link.text)

                rows = client.get(
                    "/api/v1/medium-term/unlinked-segments",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                ).json()

                demand = client.get("/api/v1/demands/DMO-274-UNLINKED").json()

            remaining = {row["segment_id"] for row in rows}
            self.assertNotIn("SEG-274-UNLINKED", remaining)
            self.assertNotIn("SEG-274-ADHOC", remaining)
            self.assertIn("SEG-274-BROKEN", remaining)
            self.assertEqual(demand["work_package_ref"], "EFF-274")
            self.assertEqual(demand["status"], "Soumise")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from datetime import date
import unittest

from sqlalchemy import select

from app.application.commands import DemandCreateCommand, DemandUpdateCommand
from app.application.read_models import DemandReadModel
from app.infrastructure.sql import (
    Base,
    Project,
    SqlDemandRepository,
    WorkforceRequest,
    WorkPackage,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.server.schemas import DemandCreateRequest, DemandUpdateRequest


class DemandWorkPackageLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with transactional_session(self.factory) as session:
            session.add_all(
                [
                    Project(id="P1", number="P-1", name="Projet 1"),
                    Project(id="P2", number="P-2", name="Projet 2"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkPackage(
                        id="WP1",
                        project_id="P1",
                        name="Programmation phase 1",
                        legacy_effort_id="EFF-1",
                        start_date=date(2026, 9, 7),
                        end_date=date(2026, 9, 11),
                    ),
                    WorkPackage(
                        id="WP2",
                        project_id="P2",
                        name="Installation phase 2",
                        legacy_effort_id="EFF-2",
                    ),
                ]
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_application_command_preserves_stable_work_package_reference(self) -> None:
        create = DemandCreateCommand.from_mapping(
            {
                "NumeroProjet": "P-1",
                "SourceEffortID": " EFF-1 ",
                "DateDebutSouhaitee": "2026-09-07",
            }
        )
        self.assertEqual(create.work_package_ref, "EFF-1")
        self.assertEqual(create.to_repository_values()["SourceEffortID"], "EFF-1")

        update = DemandUpdateCommand.from_mapping(
            "DMO-1",
            {"SourceEffortID": "EFF-2"},
        )
        self.assertEqual(update.work_package_ref, "EFF-2")
        self.assertEqual(update.to_repository_values(), {"SourceEffortID": "EFF-2"})

        clear = DemandUpdateCommand.from_mapping(
            "DMO-1",
            {"SourceEffortID": None},
        )
        self.assertIsNone(clear.work_package_ref)
        self.assertEqual(clear.to_repository_values(), {"SourceEffortID": None})

    def test_excel_read_model_projects_source_effort_id_as_work_package_ref(self) -> None:
        row = DemandReadModel.from_mapping(
            {
                "NoDemande": "DMO-1",
                "Statut": "Brouillon",
                "SourceEffortID": "EFF-1",
            }
        )
        self.assertEqual(row.work_package_ref, "EFF-1")

    def test_sql_repository_resolves_legacy_work_package_reference(self) -> None:
        with transactional_session(self.factory) as session:
            repository = SqlDemandRepository(session, actor_name="coord-test-user")
            number = repository.create(
                {
                    "NumeroProjet": "P-1",
                    "SourceEffortID": "EFF-1",
                    "DateDebutSouhaitee": date(2026, 9, 7),
                    "NombreRessources": 1,
                }
            )

            stored = session.scalar(
                select(WorkforceRequest).where(
                    WorkforceRequest.legacy_demand_number == number
                )
            )
            assert stored is not None
            self.assertEqual(stored.work_package_id, "WP1")

            read = repository.get(number)
            assert read is not None
            self.assertEqual(read.work_package_ref, "EFF-1")
            self.assertEqual(read.work_package_name, "Programmation phase 1")

    def test_project_change_clears_incompatible_work_package_unless_reselected(self) -> None:
        with transactional_session(self.factory) as session:
            repository = SqlDemandRepository(session)
            number = repository.create(
                {
                    "NumeroProjet": "P-1",
                    "SourceEffortID": "EFF-1",
                    "DateDebutSouhaitee": date(2026, 9, 7),
                }
            )
            repository.update(
                number,
                {"NumeroProjet": "P-2"},
                action="Modification",
            )
            stored = session.scalar(
                select(WorkforceRequest).where(
                    WorkforceRequest.legacy_demand_number == number
                )
            )
            assert stored is not None
            self.assertEqual(stored.project_id, "P2")
            self.assertIsNone(stored.work_package_id)

            repository.update(
                number,
                {"SourceEffortID": "EFF-2"},
                action="Modification",
            )
            self.assertEqual(stored.work_package_id, "WP2")

    def test_cross_project_work_package_is_rejected(self) -> None:
        with transactional_session(self.factory) as session:
            repository = SqlDemandRepository(session)
            with self.assertRaises(ValueError):
                repository.create(
                    {
                        "NumeroProjet": "P-1",
                        "SourceEffortID": "EFF-2",
                        "DateDebutSouhaitee": date(2026, 9, 7),
                    }
                )

    def test_http_schema_exposes_transport_neutral_work_package_reference(self) -> None:
        create = DemandCreateRequest(
            project_number="P-1",
            desired_start=date(2026, 9, 7),
            work_package_ref="EFF-1",
        )
        self.assertEqual(create.model_dump()["work_package_ref"], "EFF-1")

        update = DemandUpdateRequest(work_package_ref=None)
        self.assertIn("work_package_ref", update.model_dump(exclude_unset=True))
        self.assertIsNone(update.model_dump(exclude_unset=True)["work_package_ref"])


if __name__ == "__main__":
    unittest.main()

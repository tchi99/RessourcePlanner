from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.application.approval_cycles import (
    ApprovalCycleService,
    ApprovalApproverSnapshot,
    ApprovalCycleRecord,
    ApprovalCycleRequestRecord,
    ApprovalRequirementRecord,
)
from app.application.approval_voting import (
    APPROVAL_DECISION_APPROVE,
    ApprovalDecisionRecord,
    ApprovalVoteCommand,
    ApprovalVoteService,
    project_approval_quorum,
)
from app.application.approval_scopes import ApprovalScopeService
from app.application.errors import (
    ApplicationAuthorizationError,
    ApplicationConflictError,
    ApplicationValidationError,
)
from app.infrastructure.sql import (
    AppUser,
    ApprovalDecision,
    ApprovalScope,
    ApprovalScopeApprover,
    Base,
    Project,
    RequestApprovalCycle,
    RequestApprovalRevision,
    RequestLine,
    SqlApprovalCycleRepository,
    SqlApprovalScopeRepository,
    SqlPlanningMutationVersionRepository,
    TaskApprovalScopeMapping,
    TaskCatalogEntry,
    WorkforceRequest,
    create_sql_engine,
)


def _requirement(
    requirement_id: str,
    line_id: str,
    *approvers: str,
) -> ApprovalRequirementRecord:
    return ApprovalRequirementRecord(
        id=requirement_id,
        request_line_id=line_id,
        task_catalog_item_id=None,
        approval_scope_id="SCOPE",
        proposed_resource_id=None,
        routing_sources=("APPROVAL_SCOPE",),
        approvers=tuple(
            ApprovalApproverSnapshot(
                app_user_id=user_id,
                sources=("APPROVAL_SCOPE",),
            )
            for user_id in approvers
        ),
    )


def _cycle() -> ApprovalCycleRecord:
    return ApprovalCycleRecord(
        id="C1",
        workforce_request_id="D1",
        submitted_request_version=3,
        state="OPEN",
        subject_fingerprint="fp",
        initialization_reason="SUBMISSION",
        submitted_at=None,
        invalidated_at=None,
        invalidation_reason=None,
        completed_at=None,
        approved_revision_id=None,
        requirements=(
            _requirement("Q1", "L1", "U1", "U2"),
            _requirement("Q2", "L2", "U1"),
            _requirement("Q3", "L3", "U3"),
        ),
    )


class _Cycles:
    def __init__(self) -> None:
        self.cycle = _cycle()
        self.request = ApprovalCycleRequestRecord(
            id="D1",
            number="DMO-1",
            status="Soumise",
            aggregate_version=3,
            project_id="P1",
            priority="Normale",
            site_client=None,
            location=None,
            line_mode=True,
            approved_at=None,
        )
        self.current_fingerprint = "fp"
        self.invalidated = False

    def get_request(self, request_id: str):
        return self.request if request_id in {"D1", "DMO-1"} else None

    def get_active_cycle(self, request_id: str):
        if self.invalidated or request_id != "D1":
            return None
        return self.cycle

    def current_subject_fingerprint(self, request_id: str) -> str:
        return self.current_fingerprint

    def invalidate_cycle(self, request_id: str, *, expected_version: int, reason: str):
        if expected_version != self.request.aggregate_version:
            raise AssertionError("unexpected CAS")
        self.invalidated = True
        self.request = replace(
            self.request,
            aggregate_version=self.request.aggregate_version + 1,
        )
        return replace(
            self.cycle,
            state="INVALIDATED",
            invalidation_reason=reason,
        )

    def legacy_compatibility_state(self, request_id: str) -> str:
        return "SUBMITTED_REQUIRES_INITIALIZATION"


class _Repository:
    def __init__(self, *, active: bool = True) -> None:
        self.active = active
        self.decisions: list[ApprovalDecisionRecord] = []
        self.request_version = 3
        self.approved = False
        self.completed = False
        self.revision_id = "REV-1"
        self.audit: list[dict[str, object]] = []
        self.append_batches: list[tuple[str, ...]] = []

    def actor_is_active(self, app_user_id: str) -> bool:
        return self.active

    def list_decisions(self, cycle_id: str):
        return tuple(self.decisions)

    def acquire_request_version(self, request_id: str, expected_version: int) -> int:
        if expected_version != self.request_version:
            raise AssertionError("unexpected request CAS")
        self.request_version += 1
        return self.request_version

    def append_decisions(
        self,
        *,
        cycle_id: str,
        requirement_ids,
        app_user_id: str,
        decision: str,
        comment: str,
        action_id: str,
    ) -> None:
        self.append_batches.append(tuple(requirement_ids))
        self.decisions.extend(
            ApprovalDecisionRecord(
                requirement_id=requirement_id,
                app_user_id=app_user_id,
                decision=decision,
                action_id=action_id,
            )
            for requirement_id in requirement_ids
        )

    def mark_request_approved(self, request_id: str, *, actor_name: str, comment: str) -> None:
        self.approved = True

    def active_revision_id(self, request_id: str) -> str | None:
        return self.revision_id if self.approved else None

    def complete_cycle(
        self,
        *,
        cycle_id: str,
        approval_revision_id: str,
        action_id: str,
        planning_version: int | None,
    ) -> None:
        self.completed = True

    def append_vote_audit(self, **values) -> None:
        self.audit.append(values)


class _PlanningVersions:
    def __init__(self) -> None:
        self.calls: list[int | None] = []

    def acquire(self, expected_version: int | None = None) -> int:
        self.calls.append(expected_version)
        return 11


class _ApprovedSync:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def sync_approved(
        self,
        demand_number: str,
        *,
        approved_request_version: int | None = None,
    ) -> None:
        self.calls.append((demand_number, approved_request_version))

    def sync_operational_choices(self, demand_number: str) -> None:
        raise AssertionError("not used")


class _Planning:
    def __init__(self) -> None:
        self.calls = 0

    def rebuild(self):
        self.calls += 1
        return {"segments": 3, "allocations": 3}


class ApprovalQuorumProjectionTests(unittest.TestCase):
    def test_and_between_requirements_or_between_approvers(self) -> None:
        cycle = _cycle()
        partial = project_approval_quorum(
            cycle,
            (
                ApprovalDecisionRecord("Q1", "U2", "APPROVE", "A1"),
                ApprovalDecisionRecord("Q2", "U1", "APPROVE", "A2"),
            ),
        )
        self.assertEqual(partial.satisfied_requirements, 2)
        self.assertEqual(partial.remaining_requirement_ids, ("Q3",))
        self.assertFalse(partial.complete)

        complete = project_approval_quorum(
            cycle,
            (
                ApprovalDecisionRecord("Q1", "U2", "APPROVE", "A1"),
                ApprovalDecisionRecord("Q2", "U1", "APPROVE", "A2"),
                ApprovalDecisionRecord("Q3", "U3", "APPROVE", "A3"),
            ),
        )
        self.assertTrue(complete.complete)

    def test_non_snapshot_and_non_positive_decisions_do_not_satisfy(self) -> None:
        quorum = project_approval_quorum(
            _cycle(),
            (
                ApprovalDecisionRecord("Q1", "U3", "APPROVE", "A1"),
                ApprovalDecisionRecord("Q2", "U1", "REJECT", "A2"),
            ),
        )
        self.assertEqual(quorum.satisfied_requirements, 0)
        self.assertEqual(set(quorum.remaining_requirement_ids), {"Q1", "Q2", "Q3"})


class ApprovalVoteServiceTests(unittest.TestCase):
    def _service(
        self,
        *,
        actor: str = "U1",
        permissions=("approve_demands",),
        active: bool = True,
    ):
        cycles = _Cycles()
        repository = _Repository(active=active)
        planning_versions = _PlanningVersions()
        approved_sync = _ApprovedSync()
        planning = _Planning()
        service = ApprovalVoteService(
            cycles=cycles,
            repository=repository,
            planning_versions=planning_versions,
            approved_sync=approved_sync,
            planning=planning,
            current_user_id=actor,
            current_user_name="Même nom affiché",
            permissions=permissions,
        )
        return service, cycles, repository, planning_versions, approved_sync, planning

    def test_multi_line_partial_vote_is_atomic_and_does_not_touch_planning(self) -> None:
        service, _cycles, repository, versions, sync, planning = self._service()
        result = service.vote(
            ApprovalVoteCommand(
                workforce_request_id="D1",
                approval_cycle_id="C1",
                expected_request_version=3,
                requirement_ids=("Q1", "Q2"),
                comment="ok",
            )
        )

        self.assertFalse(result.quorum.complete)
        self.assertEqual(result.status, "Soumise")
        self.assertEqual(repository.request_version, 4)
        self.assertEqual(repository.append_batches, [("Q1", "Q2")])
        action_ids = {row.action_id for row in repository.decisions}
        self.assertEqual(len(action_ids), 1)
        self.assertIsNotNone(next(iter(action_ids)))
        self.assertEqual(versions.calls, [])
        self.assertEqual(sync.calls, [])
        self.assertEqual(planning.calls, 0)
        self.assertFalse(repository.approved)
        self.assertFalse(repository.completed)

    def test_ineligible_multi_line_batch_writes_nothing(self) -> None:
        service, _cycles, repository, versions, sync, planning = self._service()
        with self.assertRaises(ApplicationAuthorizationError) as error:
            service.vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id="C1",
                    expected_request_version=3,
                    requirement_ids=("Q1", "Q3"),
                )
            )
        self.assertEqual(error.exception.code, "approval_actor_not_eligible")
        self.assertEqual(repository.decisions, [])
        self.assertEqual(repository.request_version, 3)
        self.assertEqual(versions.calls, [])
        self.assertEqual(sync.calls, [])
        self.assertEqual(planning.calls, 0)

    def test_one_of_multiple_snapshot_approvers_is_sufficient(self) -> None:
        service, _cycles, repository, versions, _sync, _planning = self._service(actor="U2")
        result = service.vote(
            ApprovalVoteCommand(
                workforce_request_id="D1",
                approval_cycle_id="C1",
                expected_request_version=3,
                requirement_ids=("Q1",),
            )
        )
        self.assertEqual(result.quorum.satisfied_requirement_ids, ("Q1",))
        self.assertEqual(result.quorum.remaining_requirement_ids, ("Q2", "Q3"))
        self.assertEqual(versions.calls, [])
        self.assertEqual(repository.decisions[0].app_user_id, "U2")

    def test_last_vote_acquires_planning_guard_and_finalizes_once(self) -> None:
        service, _cycles, repository, versions, sync, planning = self._service(actor="U3")
        repository.decisions.extend(
            (
                ApprovalDecisionRecord("Q1", "U1", "APPROVE", "A1"),
                ApprovalDecisionRecord("Q2", "U1", "APPROVE", "A1"),
            )
        )
        result = service.vote(
            ApprovalVoteCommand(
                workforce_request_id="D1",
                approval_cycle_id="C1",
                expected_request_version=3,
                requirement_ids=("Q3",),
                expected_planning_version=10,
            )
        )

        self.assertTrue(result.quorum.complete)
        self.assertEqual(result.status, "En planification")
        self.assertEqual(result.planning_version, 11)
        self.assertEqual(result.approval_revision_id, "REV-1")
        self.assertEqual(versions.calls, [10])
        self.assertEqual(sync.calls, [("DMO-1", 3)])
        self.assertEqual(planning.calls, 1)
        self.assertTrue(repository.approved)
        self.assertTrue(repository.completed)

    def test_global_action_approves_only_requirements_where_actor_is_snapshot_eligible(self) -> None:
        service, _cycles, repository, versions, _sync, _planning = self._service(actor="U1")
        result = service.approve_all_eligible(
            workforce_request_id="D1",
            approval_cycle_id="C1",
            expected_request_version=3,
        )
        self.assertEqual(repository.append_batches, [("Q1", "Q2")])
        self.assertFalse(result.quorum.complete)
        self.assertEqual(result.quorum.remaining_requirement_ids, ("Q3",))
        self.assertEqual(versions.calls, [])

    def test_permission_active_user_and_stable_id_are_required(self) -> None:
        service, _cycles, repository, *_ = self._service(permissions=())
        with self.assertRaises(ApplicationAuthorizationError) as permission:
            service.vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id="C1",
                    expected_request_version=3,
                    requirement_ids=("Q1",),
                )
            )
        self.assertEqual(permission.exception.code, "approval_permission_required")
        self.assertEqual(repository.decisions, [])

        service, _cycles, repository, *_ = self._service(active=False)
        with self.assertRaises(ApplicationAuthorizationError) as inactive:
            service.vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id="C1",
                    expected_request_version=3,
                    requirement_ids=("Q1",),
                )
            )
        self.assertEqual(inactive.exception.code, "approval_actor_inactive")
        self.assertEqual(repository.decisions, [])

        service, _cycles, repository, *_ = self._service(actor="U3")
        with self.assertRaises(ApplicationAuthorizationError):
            service.vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id="C1",
                    expected_request_version=3,
                    requirement_ids=("Q1",),
                )
            )
        self.assertEqual(repository.decisions, [])

    def test_subject_change_invalidates_cycle_without_writing_vote(self) -> None:
        service, cycles, repository, versions, sync, planning = self._service()
        cycles.current_fingerprint = "changed"
        result = service.vote(
            ApprovalVoteCommand(
                workforce_request_id="D1",
                approval_cycle_id="C1",
                expected_request_version=3,
                requirement_ids=("Q1",),
            )
        )
        self.assertEqual(result.conflict_code, "approval_cycle_subject_changed")
        self.assertTrue(cycles.invalidated)
        self.assertEqual(repository.decisions, [])
        self.assertEqual(versions.calls, [])
        self.assertEqual(sync.calls, [])
        self.assertEqual(planning.calls, 0)

    def test_only_positive_decision_is_supported_in_276c(self) -> None:
        service, _cycles, repository, *_ = self._service()
        with self.assertRaises(ApplicationValidationError) as error:
            service.vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id="C1",
                    expected_request_version=3,
                    requirement_ids=("Q1",),
                    decision="REJECT",
                )
            )
        self.assertEqual(error.exception.code, "approval_decision_unsupported")
        self.assertEqual(repository.decisions, [])


class _UnexpectedApprovedSync:
    def sync_approved(
        self,
        demand_number: str,
        *,
        approved_request_version: int | None = None,
    ) -> None:
        raise AssertionError("approval sync must not run")

    def sync_operational_choices(self, demand_number: str) -> None:
        raise AssertionError("operational sync must not run")


class _UnexpectedPlanning:
    def rebuild(self):
        raise AssertionError("planning rebuild must not run")


class _FailingPlanning:
    def rebuild(self):
        raise RuntimeError("forced finalization failure")


class ApprovalVoteSqlConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        path = Path(self._temp.name) / "approval-vote-sql.db"
        self.engine = create_sql_engine(
            "sqlite+pysqlite:///" + path.as_posix()
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        with self.factory.begin() as session:
            self._seed(session)

    def tearDown(self) -> None:
        self.engine.dispose()
        self._temp.cleanup()

    @staticmethod
    def _seed(session) -> None:
        session.add(Project(id="P1", number="P-1", name="Projet"))
        for user_id in ("U1", "U2"):
            session.add(
                AppUser(
                    id=user_id,
                    issuer="urn:test",
                    subject=f"subject-{user_id}",
                    display_name=user_id,
                    roles_json=json.dumps(["MANAGER"]),
                    active=True,
                )
            )
        session.add_all(
            [
                TaskCatalogEntry(
                    id="T1",
                    project_number="P-1",
                    task_code="210",
                    label="Automatisation",
                    active=True,
                ),
                TaskCatalogEntry(
                    id="T2",
                    project_number="P-1",
                    task_code="110",
                    label="Installation",
                    active=True,
                ),
                ApprovalScope(
                    id="S1",
                    code="AUTOMATION",
                    label="Automatisation",
                    active=True,
                ),
                ApprovalScope(
                    id="S2",
                    code="ELECTRICAL",
                    label="Installation",
                    active=True,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                TaskApprovalScopeMapping(
                    task_catalog_item_id="T1",
                    approval_scope_id="S1",
                ),
                TaskApprovalScopeMapping(
                    task_catalog_item_id="T2",
                    approval_scope_id="S2",
                ),
                ApprovalScopeApprover(
                    approval_scope_id="S1",
                    app_user_id="U1",
                ),
                ApprovalScopeApprover(
                    approval_scope_id="S2",
                    app_user_id="U2",
                ),
            ]
        )
        session.add(
            WorkforceRequest(
                id="D1",
                legacy_demand_number="DMO-1",
                project_id="P1",
                status="Soumise",
                aggregate_version=1,
                line_mode=True,
            )
        )
        session.add_all(
            [
                RequestLine(
                    id="L1",
                    workforce_request_id="D1",
                    position=0,
                    kind="WORKFORCE",
                    desired_start=date(2026, 10, 1),
                    desired_end=date(2026, 10, 1),
                    estimated_hours=8,
                    task_catalog_item_id="T1",
                    erp_task_code="210",
                    active=True,
                ),
                RequestLine(
                    id="L2",
                    workforce_request_id="D1",
                    position=1,
                    kind="WORKFORCE",
                    desired_start=date(2026, 10, 2),
                    desired_end=date(2026, 10, 2),
                    estimated_hours=8,
                    task_catalog_item_id="T2",
                    erp_task_code="110",
                    active=True,
                ),
            ]
        )

    @staticmethod
    def _cycles(session, actor_id: str) -> ApprovalCycleService:
        return ApprovalCycleService(
            SqlApprovalCycleRepository(
                session,
                actor_user_id=actor_id,
                actor_name=actor_id,
            ),
            ApprovalScopeService(SqlApprovalScopeRepository(session)),
        )

    def _initialize(self):
        with self.factory.begin() as session:
            cycle = self._cycles(session, "U1").initialize_cycle(
                "D1",
                expected_version=1,
            )
            cycle_id = cycle.id
            requirement_by_line = {
                row.request_line_id: row.id
                for row in cycle.requirements
            }
        return cycle_id, requirement_by_line

    def _vote_service(
        self,
        session,
        *,
        actor_id: str,
        planning,
        approved_sync,
    ) -> ApprovalVoteService:
        repository = SqlApprovalCycleRepository(
            session,
            actor_user_id=actor_id,
            actor_name=actor_id,
        )
        return ApprovalVoteService(
            cycles=ApprovalCycleService(
                repository,
                ApprovalScopeService(SqlApprovalScopeRepository(session)),
            ),
            repository=repository,
            planning_versions=SqlPlanningMutationVersionRepository(session),
            approved_sync=approved_sync,
            planning=planning,
            current_user_id=actor_id,
            current_user_name=actor_id,
            permissions=("approve_demands",),
        )

    def test_stale_last_vote_rolls_back_planning_guard_and_writes_no_decision(self) -> None:
        cycle_id, requirements = self._initialize()

        with self.factory.begin() as session:
            partial = self._vote_service(
                session,
                actor_id="U1",
                planning=_UnexpectedPlanning(),
                approved_sync=_UnexpectedApprovedSync(),
            ).vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id=cycle_id,
                    expected_request_version=2,
                    requirement_ids=(requirements["L1"],),
                )
            )
            self.assertFalse(partial.quorum.complete)
            self.assertEqual(partial.request_version, 3)

        stale_session = self.factory()
        try:
            with self.assertRaises(ApplicationConflictError) as caught:
                with stale_session.begin():
                    self._vote_service(
                        stale_session,
                        actor_id="U2",
                        planning=_UnexpectedPlanning(),
                        approved_sync=_UnexpectedApprovedSync(),
                    ).vote(
                        ApprovalVoteCommand(
                            workforce_request_id="D1",
                            approval_cycle_id=cycle_id,
                            expected_request_version=2,
                            requirement_ids=(requirements["L2"],),
                            expected_planning_version=1,
                        )
                    )
            self.assertEqual(caught.exception.code, "demand_version_conflict")
        finally:
            stale_session.close()

        with self.factory() as session:
            request = session.get(WorkforceRequest, "D1")
            self.assertEqual(request.status, "Soumise")
            self.assertEqual(request.aggregate_version, 3)
            decisions = session.scalars(select(ApprovalDecision)).all()
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0].app_user_id, "U1")
            self.assertEqual(
                SqlPlanningMutationVersionRepository(session).current_version(),
                1,
            )

    def test_finalization_failure_rolls_back_last_vote_status_cycle_and_planning_version(self) -> None:
        cycle_id, requirements = self._initialize()

        with self.factory.begin() as session:
            self._vote_service(
                session,
                actor_id="U1",
                planning=_UnexpectedPlanning(),
                approved_sync=_UnexpectedApprovedSync(),
            ).vote(
                ApprovalVoteCommand(
                    workforce_request_id="D1",
                    approval_cycle_id=cycle_id,
                    expected_request_version=2,
                    requirement_ids=(requirements["L1"],),
                )
            )

        session = self.factory()
        try:
            with self.assertRaises(RuntimeError):
                with session.begin():
                    self._vote_service(
                        session,
                        actor_id="U2",
                        planning=_FailingPlanning(),
                        approved_sync=type(
                            "_NoopApprovedSync",
                            (),
                            {
                                "sync_approved": lambda self, demand_number, approved_request_version=None: None,
                                "sync_operational_choices": lambda self, demand_number: None,
                            },
                        )(),
                    ).vote(
                        ApprovalVoteCommand(
                            workforce_request_id="D1",
                            approval_cycle_id=cycle_id,
                            expected_request_version=3,
                            requirement_ids=(requirements["L2"],),
                            expected_planning_version=1,
                        )
                    )
        finally:
            session.close()

        with self.factory() as check:
            request = check.get(WorkforceRequest, "D1")
            cycle = check.get(RequestApprovalCycle, cycle_id)
            self.assertEqual(request.status, "Soumise")
            self.assertEqual(request.aggregate_version, 3)
            self.assertEqual(cycle.state, "OPEN")
            self.assertIsNone(cycle.approved_revision_id)
            self.assertEqual(
                check.scalar(select(func.count(ApprovalDecision.id))),
                1,
            )
            self.assertEqual(
                check.scalar(select(func.count(RequestApprovalRevision.id))),
                0,
            )
            self.assertEqual(
                SqlPlanningMutationVersionRepository(check).current_version(),
                1,
            )


if __name__ == "__main__":
    unittest.main()

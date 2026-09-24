from __future__ import annotations

import unittest

from app.application.demand_workflow_policy import (
    ACTION_APPROVE,
    ACTION_CANCEL,
    ACTION_CORRECTION,
    ACTION_EMERGENCY_PLAN,
    ACTION_REJECT_CANCELLATION,
    ACTION_REQUEST_CANCELLATION,
    ACTION_MODIFY,
    ACTION_SUBMIT,
    assert_demand_action,
    demand_workflow_state,
)
from app.application.errors import (
    ApplicationAuthorizationError,
    ApplicationConflictError,
)
from app.application.query_models import DemandCancellationMaterializationReadModel
from app.application.read_models import DemandReadModel
from app.application.security import (
    ROLE_ADMIN,
    ROLE_COORDINATOR,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    permissions_for_roles,
)


class DemandWorkflowPolicyTests(unittest.TestCase):
    def test_draft_actions_combine_state_and_project_manager_permissions(self) -> None:
        state = demand_workflow_state(
            DemandReadModel(number="DMO-1", status="Brouillon", version=3),
            permissions=permissions_for_roles((ROLE_PROJECT_MANAGER,)),
        )

        self.assertEqual(
            set(state.available_actions),
            {ACTION_MODIFY, ACTION_SUBMIT, ACTION_CANCEL},
        )
        decisions = {row.action: row for row in state.actions}
        self.assertEqual(decisions[ACTION_APPROVE].reason_code, "permission_denied")
        self.assertEqual(decisions[ACTION_CORRECTION].reason_code, "permission_denied")
        self.assertEqual(decisions[ACTION_EMERGENCY_PLAN].reason_code, "permission_denied")
        self.assertEqual(state.version, 3)

    def test_submitted_manager_can_approve_or_request_correction_but_not_manage(self) -> None:
        state = demand_workflow_state(
            DemandReadModel(number="DMO-2", status="Soumise"),
            permissions=permissions_for_roles((ROLE_MANAGER,)),
        )

        self.assertIn(ACTION_APPROVE, state.available_actions)
        self.assertIn(ACTION_CORRECTION, state.available_actions)
        self.assertIn(ACTION_EMERGENCY_PLAN, state.available_actions)
        self.assertNotIn(ACTION_MODIFY, state.available_actions)
        self.assertNotIn(ACTION_CANCEL, state.available_actions)

    def test_terminal_status_has_no_available_action_even_for_admin(self) -> None:
        state = demand_workflow_state(
            DemandReadModel(number="DMO-3", status="Annulée"),
            permissions=permissions_for_roles((ROLE_ADMIN,)),
        )

        self.assertEqual(state.available_actions, ())
        self.assertTrue(
            all(row.reason_code == "demand_transition_invalid" for row in state.actions)
        )

    def test_materialized_demand_requires_cancellation_request_instead_of_direct_cancel(self) -> None:
        state = demand_workflow_state(
            DemandReadModel(number="DMO-MAT", status="En planification", version=4),
            permissions=permissions_for_roles((ROLE_PROJECT_MANAGER,)),
            materialization=DemandCancellationMaterializationReadModel(
                demand_number="DMO-MAT",
                human_shift_count=1,
                locked_human_shift_count=1,
            ),
        )

        self.assertNotIn(ACTION_CANCEL, state.available_actions)
        self.assertIn(ACTION_REQUEST_CANCELLATION, state.available_actions)
        self.assertTrue(state.cancellation.has_operational_decisions)
        self.assertFalse(state.cancellation.direct_cancel)
        self.assertTrue(state.cancellation.request_cancellation)

    def test_pending_cancellation_exposes_resolution_only_to_coordinator(self) -> None:
        demand = DemandReadModel(
            number="DMO-PENDING",
            status="En planification",
            version=5,
            cancellation_request_id="11111111-1111-1111-1111-111111111111",
            cancellation_state="PENDING",
        )
        materialization = DemandCancellationMaterializationReadModel(
            demand_number=demand.number,
            asset_allocation_count=1,
        )

        coordinator = demand_workflow_state(
            demand,
            permissions=permissions_for_roles((ROLE_COORDINATOR,)),
            materialization=materialization,
        )
        project_manager = demand_workflow_state(
            demand,
            permissions=permissions_for_roles((ROLE_PROJECT_MANAGER,)),
            materialization=materialization,
        )

        self.assertIn(ACTION_REJECT_CANCELLATION, coordinator.available_actions)
        self.assertNotIn(ACTION_REQUEST_CANCELLATION, coordinator.available_actions)
        self.assertNotIn(ACTION_CANCEL, coordinator.available_actions)
        self.assertTrue(coordinator.cancellation.cancellation_pending)
        self.assertTrue(coordinator.cancellation.resolve_cancellation)
        self.assertNotIn(ACTION_REJECT_CANCELLATION, project_manager.available_actions)
        rejection = {
            row.action: row for row in project_manager.actions
        }[ACTION_REJECT_CANCELLATION]
        self.assertEqual(rejection.reason_code, "permission_denied")
        self.assertEqual(
            set(rejection.required_permissions),
            {"approve_demands", "manage_planning"},
        )

    def test_invalid_direct_transition_is_conflict(self) -> None:
        with self.assertRaises(ApplicationConflictError) as raised:
            assert_demand_action(
                DemandReadModel(number="DMO-4", status="Brouillon", version=2),
                ACTION_APPROVE,
                permissions=permissions_for_roles((ROLE_ADMIN,)),
            )

        self.assertEqual(raised.exception.code, "demand_transition_invalid")
        self.assertEqual(raised.exception.context["status"], "Brouillon")
        self.assertEqual(raised.exception.context["version"], 2)

    def test_missing_permission_is_authorization_error(self) -> None:
        with self.assertRaises(ApplicationAuthorizationError) as raised:
            assert_demand_action(
                DemandReadModel(number="DMO-5", status="Soumise"),
                ACTION_APPROVE,
                permissions=permissions_for_roles((ROLE_PROJECT_MANAGER,)),
            )

        self.assertEqual(raised.exception.code, "permission_denied")
        self.assertEqual(
            raised.exception.context["required_permission"],
            "approve_demands",
        )


if __name__ == "__main__":
    unittest.main()

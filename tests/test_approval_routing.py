from __future__ import annotations

import unittest

from app.domain.approval_routing import (
    APPROVAL_SCOPE_CODE_AUTOMATION,
    APPROVAL_SCOPE_CODE_ELECTRICAL_INSTALLATION,
    APPROVER_SOURCE_RESOURCE,
    APPROVER_SOURCE_SCOPE,
    ApprovalRoutingUser,
    ApprovalScopeCandidate,
    DIAGNOSTIC_APPROVER_INACTIVE,
    DIAGNOSTIC_APPROVER_PERMISSION_MISSING,
    DIAGNOSTIC_NO_ELIGIBLE_APPROVER,
    DIAGNOSTIC_SCOPE_AMBIGUOUS,
    DIAGNOSTIC_SCOPE_INACTIVE,
    DIAGNOSTIC_SCOPE_UNMAPPED,
    resolve_line_approvers,
    suggested_approval_scope_code,
)


class ApprovalRoutingPolicyTests(unittest.TestCase):
    def test_task_code_conventions_are_classification_suggestions_only(self) -> None:
        self.assertEqual(
            suggested_approval_scope_code("110"),
            APPROVAL_SCOPE_CODE_ELECTRICAL_INSTALLATION,
        )
        self.assertEqual(
            suggested_approval_scope_code("119"),
            APPROVAL_SCOPE_CODE_ELECTRICAL_INSTALLATION,
        )
        self.assertEqual(
            suggested_approval_scope_code("210"),
            APPROVAL_SCOPE_CODE_AUTOMATION,
        )
        self.assertEqual(
            suggested_approval_scope_code("219"),
            APPROVAL_SCOPE_CODE_AUTOMATION,
        )
        self.assertIsNone(suggested_approval_scope_code("109"))
        self.assertIsNone(
            suggested_approval_scope_code("installation 110")
        )

    def test_scope_resolution_filters_and_deduplicates_by_app_user_id(
        self,
    ) -> None:
        users = {
            "u1": ApprovalRoutingUser(
                "u1",
                True,
                ("read", "approve_demands"),
            ),
            "u2": ApprovalRoutingUser(
                "u2",
                False,
                ("approve_demands",),
            ),
            "u3": ApprovalRoutingUser(
                "u3",
                True,
                ("read",),
            ),
        }
        result = resolve_line_approvers(
            line_active=True,
            task_catalog_item_id="task-1",
            task_exists=True,
            task_active=True,
            scope_candidates=(
                ApprovalScopeCandidate("scope-a", True),
            ),
            scope_approver_user_ids=("u1", "u2", "u3"),
            users=users,
            resource_approver_user_ids=("u1",),
        )

        self.assertFalse(result.blocked)
        self.assertEqual(result.approval_scope_id, "scope-a")
        self.assertEqual(len(result.eligible_approvers), 1)
        self.assertEqual(
            result.eligible_approvers[0].user_id,
            "u1",
        )
        self.assertEqual(
            set(result.eligible_approvers[0].sources),
            {
                APPROVER_SOURCE_SCOPE,
                APPROVER_SOURCE_RESOURCE,
            },
        )
        self.assertIn(
            f"{DIAGNOSTIC_APPROVER_INACTIVE}:u2",
            result.diagnostics,
        )
        self.assertIn(
            f"{DIAGNOSTIC_APPROVER_PERMISSION_MISSING}:u3",
            result.diagnostics,
        )

    def test_unmapped_ambiguous_and_inactive_scope_are_explicit_blocks(
        self,
    ) -> None:
        common = dict(
            line_active=True,
            task_catalog_item_id="task-1",
            task_exists=True,
            task_active=True,
            scope_approver_user_ids=(),
            users={},
        )
        unmapped = resolve_line_approvers(
            scope_candidates=(),
            **common,
        )
        ambiguous = resolve_line_approvers(
            scope_candidates=(
                ApprovalScopeCandidate("a", True),
                ApprovalScopeCandidate("b", True),
            ),
            **common,
        )
        inactive = resolve_line_approvers(
            scope_candidates=(
                ApprovalScopeCandidate("a", False),
            ),
            **common,
        )

        self.assertTrue(unmapped.blocked)
        self.assertIn(
            DIAGNOSTIC_SCOPE_UNMAPPED,
            unmapped.diagnostics,
        )
        self.assertIn(
            DIAGNOSTIC_SCOPE_AMBIGUOUS,
            ambiguous.diagnostics,
        )
        self.assertIn(
            DIAGNOSTIC_SCOPE_INACTIVE,
            inactive.diagnostics,
        )

    def test_scope_with_no_admissible_user_is_blocked(self) -> None:
        result = resolve_line_approvers(
            line_active=True,
            task_catalog_item_id="task-1",
            task_exists=True,
            task_active=True,
            scope_candidates=(
                ApprovalScopeCandidate("scope-a", True),
            ),
            scope_approver_user_ids=("missing",),
            users={},
        )
        self.assertTrue(result.blocked)
        self.assertIn(
            DIAGNOSTIC_NO_ELIGIBLE_APPROVER,
            result.diagnostics,
        )


if __name__ == "__main__":
    unittest.main()
